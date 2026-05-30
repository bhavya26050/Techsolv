from __future__ import annotations

from pydantic import BaseModel, Field


class IngestRequest(BaseModel):
    video_a_url: str = Field(min_length=1)
    video_b_url: str = Field(min_length=1)


class ChatRequest(BaseModel):
    pair_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    provider: str | None = None
    model: str | None = None


class SourceChunk(BaseModel):
    video_id: str
    chunk_id: str
    chunk_index: int
    label: str
    excerpt: str
    source_url: str


class VideoMetadata(BaseModel):
    video_id: str
    label: str
    platform: str
    url: str
    title: str
    creator: str
    follower_count: int | None = None
    views: int | None = None
    likes: int = 0
    comments: int = 0
    hashtags: list[str] = Field(default_factory=list)
    upload_date: str | None = None
    duration_seconds: int | None = None
    engagement_rate: float = 0.0
    transcript_preview: str = ""
    hook_preview: str = ""
    chunk_count: int = 0


class IngestResponse(BaseModel):
    pair_id: str
    videos: list[VideoMetadata]
