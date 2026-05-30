from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

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


def selected_llm_identity(override_model: str | None = None) -> tuple[str, str]:
    """Return ('gemini', model) tuple. Overrides take precedence; otherwise env settings are used.

    Raises RuntimeError if GOOGLE_API_KEY is not configured.
    """
    config = settings()
    model = override_model or config.get("gemini_model")
    if config.get("google_api_key"):
        return ("gemini", model)
    raise RuntimeError("Set GOOGLE_API_KEY to use Gemini.")


def _build_model(override_model: str | None = None):
    _, model_name = selected_llm_identity(override_model)
    config = settings()
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=config["google_api_key"],
        temperature=0.2,
        streaming=True,
    )


def _messages_for_prompt(history: list[dict[str, str]], question: str, context: str) -> list[BaseMessage]:
    messages: list[BaseMessage] = [
        SystemMessage(
            content=(
                "You are a creator analytics assistant. Compare two videos using only the provided metrics, transcripts, and retrieved chunks. "
                "Always cite evidence inline using tokens like [A#0] or [B#2]. If a metric is missing or unavailable, write 'Unavailable' instead of 0. "
                "Do not calculate engagement from view counts when views are missing. If views are unavailable for a video, compare the available signals (likes, comments, creator, hook, and transcript) and say the view-based engagement rate cannot be computed. "
                "If the evidence is insufficient, say exactly what is missing rather than guessing. "
                "Format every answer in clean Markdown with this structure: "
                "1) a single-sentence Bottom line, "
                "2) a short bullet list called Key evidence, "
                "3) a short bullet list called Comparison, and "
                "4) a final Caveats section if needed. "
                "Use at most 6 bullets total. Keep each bullet to one idea. Avoid long paragraphs. "
                "Use bold only for section titles and the most important metric names."
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


def _chunk_to_text(chunk: object) -> str:
    """Normalize streaming chunks from Gemini/OpenAI-style clients into plain text."""
    content = getattr(chunk, "content", chunk)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content") or ""
                if text:
                    parts.append(str(text))
            else:
                text = getattr(item, "text", None) or getattr(item, "content", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    return str(content)


async def stream_answer(*, pair_id: str, thread_id: str, question: str, pair_payload: dict, model: str | None = None):
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
    model = _build_model(model)
    answer_parts: list[str] = []
    async for chunk in model.astream(messages):
        token = _chunk_to_text(chunk)
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
