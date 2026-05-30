from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from .config import settings
from .storage import append_message, load_messages
from .vectorstore import search_documents


@dataclass
class Citation:
    video_id: str
    chunk_id: str
    chunk_index: int
    label: str
    excerpt: str
    source_url: str


def selected_llm_identity() -> tuple[str, str]:
    config = settings()
    if config["google_api_key"]:
        return ("gemini", config["gemini_model"])
    if config["openai_api_key"]:
        return ("openai", config["openai_model"])
    raise RuntimeError("Set GOOGLE_API_KEY to use Gemini or OPENAI_API_KEY to use OpenAI.")


def _build_model():
    provider, model_name = selected_llm_identity()
    config = settings()
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=config["google_api_key"],
            temperature=0.2,
            streaming=True,
        )
    if provider == "openai":
        return ChatOpenAI(
            api_key=config["openai_api_key"],
            model=model_name,
            streaming=True,
            temperature=0.2,
        )
    raise RuntimeError("Unknown LLM provider configuration.")


def _messages_for_prompt(history: list[dict[str, str]], question: str, context: str) -> list[BaseMessage]:
    messages: list[BaseMessage] = [
        SystemMessage(
            content=(
                "You are a creator analytics assistant. Compare two videos using only the provided metrics, transcripts, and retrieved chunks. "
                "Always cite evidence inline using tokens like [A#0] or [B#2]. If the evidence is insufficient, say what is missing rather than guessing. "
                "Be concise, analytical, and specific."
            )
        )
    ]
    for item in history:
        if item["role"] == "user":
            messages.append(HumanMessage(content=item["content"]))
        else:
            messages.append(AIMessage(content=item["content"]))
    messages.append(HumanMessage(content=f"Question: {question}\n\nEvidence:\n{context}"))
    return messages


def _format_context(citations: Iterable[Citation], pair_payload: dict) -> str:
    video_map = {video["video_id"]: video for video in pair_payload["videos"]}
    lines: list[str] = []
    for citation in citations:
        video = video_map.get(citation.video_id, {})
        lines.append(
            f"[{citation.label}#{citation.chunk_index}] {video.get('title', '')} | creator={video.get('creator', '')} | views={video.get('views', 0)} | likes={video.get('likes', 0)} | comments={video.get('comments', 0)}"
        )
        lines.append(citation.excerpt.strip())
        lines.append("")
    return "\n".join(lines).strip()


async def stream_answer(*, pair_id: str, thread_id: str, question: str, pair_payload: dict):
    history = load_messages(pair_id, thread_id)
    docs = search_documents(question, pair_id=pair_id, limit=6)
    citations = [
        Citation(
            video_id=str(doc.metadata.get("video_id", "")),
            chunk_id=str(doc.metadata.get("chunk_id", "")),
            chunk_index=int(doc.metadata.get("chunk_index", 0)),
            label=str(doc.metadata.get("label", doc.metadata.get("video_id", ""))),
            excerpt=str(doc.page_content),
            source_url=str(doc.metadata.get("source_url", "")),
        )
        for doc in docs
    ]
    context = _format_context(citations, pair_payload)
    messages = _messages_for_prompt(history, question, context)
    model = _build_model()
    answer_parts: list[str] = []
    async for chunk in model.astream(messages):
        token = getattr(chunk, "content", "") or ""
        if token:
            answer_parts.append(token)
            yield token
    answer_text = "".join(answer_parts).strip()
    append_message(pair_id, thread_id, "user", question)
    append_message(pair_id, thread_id, "assistant", answer_text)


def build_citation_payload(pair_payload: dict, question: str) -> list[dict]:
    docs = search_documents(question, pair_id=pair_payload["pair_id"], limit=6)
    payload = []
    for doc in docs:
        payload.append(
            {
                "video_id": str(doc.metadata.get("video_id", "")),
                "chunk_id": str(doc.metadata.get("chunk_id", "")),
                "chunk_index": int(doc.metadata.get("chunk_index", 0)),
                "label": str(doc.metadata.get("label", doc.metadata.get("video_id", ""))),
                "excerpt": str(doc.page_content)[:320],
                "source_url": str(doc.metadata.get("source_url", "")),
            }
        )
    return payload
