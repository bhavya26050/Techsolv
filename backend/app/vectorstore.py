from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .config import settings


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
SPLITTER = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=140)


def _collection_path() -> Path:
    return Path(settings()["chroma_path"])


@lru_cache(maxsize=1)
def get_embeddings() -> HuggingFaceEmbeddings:
    return HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)


@lru_cache(maxsize=1)
def get_vectorstore() -> Chroma:
    path = _collection_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name="creator_video_chunks",
        persist_directory=str(path),
        embedding_function=get_embeddings(),
    )


def chunk_transcript(transcript_text: str, *, pair_id: str, video_id: str, label: str, source_url: str, title: str, creator: str) -> list[Document]:
    chunks = SPLITTER.split_text(transcript_text)
    documents: list[Document] = []
    for index, chunk in enumerate(chunks):
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
    store = get_vectorstore()
    store.add_documents(docs)


def search_documents(query: str, pair_id: str, limit: int = 6) -> list[Document]:
    store = get_vectorstore()
    results = store.similarity_search(query, k=limit, filter={"pair_id": pair_id})
    return results
