from __future__ import annotations

from functools import lru_cache
from math import sqrt
from typing import Iterable

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .storage import _mongo_db


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=140)


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


def _chunks_collection():
    return _mongo_db().video_chunks


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(x * y for x, y in zip(left, right))
    left_norm = sqrt(sum(x * x for x in left))
    right_norm = sqrt(sum(y * y for y in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)


def chunk_transcript(transcript_text: str, *, pair_id: str, video_id: str, label: str, source_url: str, title: str, creator: str) -> list[Document]:
    documents: list[Document] = []
    for index, chunk in enumerate(SPLITTER.split_text(transcript_text)):
        documents.append(
            Document(
                page_content=chunk,
                metadata={
                    "pair_id": pair_id,
                    "video_id": video_id,
                    "chunk_index": index,
                    "chunk_id": f"{video_id}-{index}",
                    "label": label,
                    "source_url": source_url,
                    "title": title,
                    "creator": creator,
                },
            )
        )
    return documents


def upsert_documents(documents: Iterable[Document]) -> None:
    docs = list(documents)
    if not docs:
        return
    texts = [doc.page_content for doc in docs]
    embeddings = get_embeddings().embed_documents(texts)
    collection = _chunks_collection()
    for doc, embedding in zip(docs, embeddings):
        metadata = dict(doc.metadata)
        collection.update_one(
            {"pair_id": metadata["pair_id"], "chunk_id": metadata["chunk_id"]},
            {
                "$set": {
                    "pair_id": metadata["pair_id"],
                    "video_id": metadata["video_id"],
                    "chunk_id": metadata["chunk_id"],
                    "chunk_index": metadata["chunk_index"],
                    "label": metadata["label"],
                    "source_url": metadata["source_url"],
                    "title": metadata["title"],
                    "creator": metadata["creator"],
                    "page_content": doc.page_content,
                    "embedding": embedding,
                }
            },
            upsert=True,
        )


def search_documents(query: str, pair_id: str, limit: int = 6) -> list[Document]:
    query_embedding = get_embeddings().embed_query(query)
    docs = list(
        _chunks_collection().find(
            {"pair_id": pair_id},
            {"_id": 0, "page_content": 1, "embedding": 1, "video_id": 1, "chunk_id": 1, "chunk_index": 1, "label": 1, "source_url": 1, "title": 1, "creator": 1},
        )
    )
    scored: list[tuple[float, Document]] = []
    for item in docs:
        embedding = [float(value) for value in item.get("embedding", [])]
        score = _cosine_similarity(query_embedding, embedding)
        scored.append(
            (
                score,
                Document(
                    page_content=str(item.get("page_content", "")),
                    metadata={
                        "pair_id": pair_id,
                        "video_id": str(item.get("video_id", "")),
                        "chunk_id": str(item.get("chunk_id", "")),
                        "chunk_index": int(item.get("chunk_index", 0)),
                        "label": str(item.get("label", "")),
                        "source_url": str(item.get("source_url", "")),
                        "title": str(item.get("title", "")),
                        "creator": str(item.get("creator", "")),
                    },
                ),
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for _, doc in scored[:limit]]
