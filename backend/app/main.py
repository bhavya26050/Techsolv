from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.documents import Document

from .metadata import inspect_video
from .budget import credit_status, estimate_credits_used_usd, estimate_tokens_from_text, minimum_remaining_credit_usd
from .rag import build_citation_payload, stream_answer
from .schemas import ChatRequest, IngestRequest, IngestResponse
from .storage import initialize, load_messages, load_pair, record_credit_usage, save_pair
from .transcript import segments_to_text
from .vectorstore import chunk_transcript, upsert_documents
from .rag import selected_llm_identity


app = FastAPI(title="Creator RAG Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    initialize()


def _build_video_payload(video_id: str, label: str, url: str, pair_id: str) -> tuple[dict[str, Any], list[Document]]:
    metadata, segments, _raw_info = inspect_video(url, video_id=video_id, label=label, pair_id=pair_id)
    transcript_text = segments_to_text(segments)
    if not transcript_text.strip():
        raise HTTPException(status_code=422, detail=f"No transcript or caption text could be extracted for {label}.")
    chunks = chunk_transcript(
        transcript_text,
        pair_id=pair_id,
        video_id=video_id,
        label=label,
        source_url=url,
        title=metadata.title,
        creator=metadata.creator,
    )
    metadata.chunk_count = len(chunks)
    metadata.transcript_preview = transcript_text[:500]
    metadata.hook_preview = metadata.hook_preview or transcript_text[:200]
    return metadata.model_dump(), chunks


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    pair_id = str(uuid.uuid4())
    video_a_payload, chunks_a = _build_video_payload("A", "Video A", request.video_a_url, pair_id)
    video_b_payload, chunks_b = _build_video_payload("B", "Video B", request.video_b_url, pair_id)
    pair_payload = {"pair_id": pair_id, "videos": [video_a_payload, video_b_payload]}
    save_pair(pair_id, pair_payload)
    upsert_documents([*chunks_a, *chunks_b])
    return IngestResponse(pair_id=pair_id, videos=[video_a_payload, video_b_payload])


@app.get("/api/pairs/{pair_id}")
def get_pair(pair_id: str) -> dict[str, Any]:
    payload = load_pair(pair_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Unknown pair_id")
    return payload


@app.get("/api/credits/{pair_id}")
def get_credits(pair_id: str, thread_id: str | None = None, provider: str | None = None) -> dict[str, float]:
    payload = load_pair(pair_id)
    if not payload:
        raise HTTPException(status_code=404, detail="Unknown pair_id")
    if provider:
        from .budget import provider_credit_status

        return provider_credit_status(pair_id, provider, thread_id)
    return credit_status(pair_id, thread_id)


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    pair_payload = load_pair(request.pair_id)
    if not pair_payload:
        raise HTTPException(status_code=404, detail="Unknown pair_id")

    # Determine provider and enforce per-provider budget (and optionally daily reset) before starting generation
    try:
        provider, model_name = selected_llm_identity()
    except RuntimeError as exc:
        # Surface a clear HTTP error so the frontend can show a user-friendly message
        raise HTTPException(status_code=503, detail=str(exc))
    from .budget import provider_credit_status

    provider_status = provider_credit_status(request.pair_id, provider, request.thread_id)
    if provider_status["remaining_usd"] <= minimum_remaining_credit_usd():
        raise HTTPException(
            status_code=402,
            detail=(
                f"Credit budget exhausted for provider '{provider}'. "
                "Increase provider budget or reduce request volume/model cost."
            ),
        )

    async def event_generator():
        history = load_messages(request.pair_id, request.thread_id)
        citations = build_citation_payload(pair_payload, request.message)
        yield f"event: sources\ndata: {json.dumps(citations)}\n\n"
        history_text = "\n".join(f"{item['role']}: {item['content']}" for item in history)
        evidence_text = "\n".join(source.get("excerpt", "") for source in citations)
        input_tokens_est = estimate_tokens_from_text(f"{history_text}\n{request.message}\n{evidence_text}")
        output_chars = 0
        async for token in stream_answer(pair_id=request.pair_id, thread_id=request.thread_id, question=request.message, pair_payload=pair_payload):
            output_chars += len(token)
            yield f"event: token\ndata: {json.dumps(token)}\n\n"
        output_tokens_est = estimate_tokens_from_text("x" * output_chars)
        credits_used_usd = estimate_credits_used_usd(input_tokens_est=input_tokens_est, output_tokens_est=output_tokens_est)
        record_credit_usage(
            pair_id=request.pair_id,
            thread_id=request.thread_id,
            provider=provider,
            model=model_name,
            input_tokens_est=input_tokens_est,
            output_tokens_est=output_tokens_est,
            credits_used_usd=credits_used_usd,
        )
        # Emit updated provider-specific and overall budget info
        from .budget import provider_credit_status
        overall = credit_status(request.pair_id, request.thread_id)
        yield f"event: budget\ndata: {json.dumps({'overall': overall, 'provider': provider_credit_status(request.pair_id, provider, request.thread_id)})}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
