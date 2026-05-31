from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
import tempfile
from pathlib import Path
from typing import Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

from .config import settings


@dataclass
class TranscriptSegment:
    start: float
    duration: float
    text: str


@lru_cache(maxsize=1)
def _cookiefile_path() -> str | None:
    cfg = settings()
    cookiefile = cfg.get("ytdlp_cookies_file", "").strip()
    if cookiefile:
        return cookiefile
    cookies_b64 = cfg.get("ytdlp_cookies_b64", "").strip()
    if not cookies_b64:
        return None
    try:
        raw = base64.b64decode(cookies_b64.encode("utf-8"), validate=True)
    except Exception:
        return None
    temp_path = Path(tempfile.gettempdir()) / "techsolv-ytdlp-cookies.txt"
    temp_path.write_bytes(raw)
    return str(temp_path)


def _ytdlp_options() -> dict[str, Any]:
    options: dict[str, Any] = {"quiet": True, "skip_download": True}
    cookiefile = _cookiefile_path()
    if cookiefile:
        options["cookiefile"] = cookiefile
    options.setdefault("noplaylist", True)
    options["extractor_args"] = {"youtube": {"player_client": ["android"]}}
    return options


def _video_id_from_info(info: dict[str, Any]) -> str:
    return str(info.get("id") or info.get("display_id") or "")


def fetch_youtube_transcript(video_url: str, info: dict[str, Any]) -> list[TranscriptSegment]:
    video_id = _video_id_from_info(info)
    if not video_id:
        return []
    api = YouTubeTranscriptApi()
    transcript = None
    for langs in (("en", "en-US", "en-GB"), ("en",), None):
        try:
            if langs is None:
                transcript = api.fetch(video_id)
            else:
                transcript = api.fetch(video_id, languages=list(langs))
            break
        except Exception:
            continue
    if transcript is None:
        raise RuntimeError(f"No transcript was available for YouTube video {video_id}")
    return [TranscriptSegment(start=float(item["start"]), duration=float(item.get("duration", 0.0)), text=str(item["text"])) for item in transcript]


def fetch_fallback_transcript(video_url: str, info: dict[str, Any]) -> list[TranscriptSegment]:
    subtitles = info.get("subtitles") or info.get("automatic_captions") or {}
    for lang_tracks in subtitles.values():
        if not lang_tracks:
            continue
        track = lang_tracks[0]
        if track.get("ext") != "vtt" and not track.get("url"):
            continue
        return _download_vtt_segments(track.get("url") or "")
    description = str(info.get("description") or "").strip()
    if description:
        return [TranscriptSegment(start=0.0, duration=0.0, text=description)]
    return []


def _download_vtt_segments(vtt_url: str) -> list[TranscriptSegment]:
    if not vtt_url:
        return []
    with yt_dlp.YoutubeDL(_ytdlp_options()) as ydl:
        payload = ydl.urlopen(vtt_url).read().decode("utf-8", errors="ignore")
    segments: list[TranscriptSegment] = []
    buffer: list[str] = []
    current_start = 0.0
    for line in payload.splitlines():
        if " --> " in line:
            time_part = line.split(" --> ", 1)[0].strip()
            current_start = _parse_vtt_timestamp(time_part)
            continue
        if not line or line.startswith("WEBVTT"):
            continue
        if line.strip().isdigit():
            continue
        buffer.append(line.strip())
        if len(buffer) >= 2:
            segments.append(TranscriptSegment(start=current_start, duration=0.0, text=" ".join(buffer)))
            buffer = []
    if buffer:
        segments.append(TranscriptSegment(start=current_start, duration=0.0, text=" ".join(buffer)))
    return segments


def _parse_vtt_timestamp(timestamp: str) -> float:
    hours, minutes, seconds = 0, 0, 0.0
    parts = timestamp.split(":")
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2].replace(",", "."))
    elif len(parts) == 2:
        minutes = int(parts[0])
        seconds = float(parts[1].replace(",", "."))
    return hours * 3600 + minutes * 60 + seconds


def segments_to_text(segments: list[TranscriptSegment]) -> str:
    return "\n".join(segment.text.strip() for segment in segments if segment.text.strip())


def first_seconds_preview(segments: list[TranscriptSegment], seconds: float = 5.0) -> str:
    if not segments:
        return ""
    preview = [segment.text.strip() for segment in segments if segment.start <= seconds and segment.text.strip()]
    if preview:
        return " ".join(preview)
    return segments[0].text.strip()
