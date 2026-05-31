from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse
from typing import Any

import instaloader
import yt_dlp

from .schemas import VideoMetadata
from .transcript import TranscriptSegment, fetch_fallback_transcript, fetch_youtube_transcript, first_seconds_preview, segments_to_text
from .transcript import _ytdlp_options


HASHTAG_RE = re.compile(r"#([A-Za-z0-9_]+)")


def _extract_platform(url: str) -> str:
    lowered = url.lower()
    if "youtube.com" in lowered or "youtu.be" in lowered:
        return "youtube"
    if "instagram.com" in lowered:
        return "instagram"
    return "unknown"


def _youtube_video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname and "youtu.be" in parsed.hostname:
        return parsed.path.lstrip("/")
    if parsed.hostname and "youtube.com" in parsed.hostname:
        query = parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/", 1)[1].split("/")[0]
    return ""


def _extract_hashtags(info: dict[str, Any]) -> list[str]:
    tags = set()
    for tag in info.get("tags") or []:
        tags.add(str(tag).lstrip("#"))
    description = str(info.get("description") or "")
    for match in HASHTAG_RE.findall(description):
        tags.add(match)
    return sorted(tags)


def _format_upload_date(info: dict[str, Any]) -> str | None:
    upload_date = info.get("upload_date")
    timestamp = info.get("timestamp")
    if upload_date:
        try:
            return datetime.strptime(str(upload_date), "%Y%m%d").date().isoformat()
        except Exception:
            return str(upload_date)
    if timestamp:
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).date().isoformat()
    return None


def _extract_info(url: str) -> dict[str, Any]:
    platform = _extract_platform(url)
    if platform == "youtube":
        video_id = _youtube_video_id_from_url(url)
        title = f"YouTube video {video_id}" if video_id else "YouTube video"
        return {
            "id": video_id,
            "display_id": video_id,
            "title": title,
            "channel": "Unavailable",
            "uploader": "Unavailable",
            "uploader_id": "",
            "webpage_url": url,
            "description": "",
            "view_count": None,
            "like_count": None,
            "comment_count": None,
            "tags": [],
            "subtitles": {},
            "automatic_captions": {},
            "duration": None,
            "timestamp": None,
            "upload_date": None,
        }
    attempts: list[dict[str, Any]] = []
    attempts.append(_ytdlp_options(use_cookies=False, player_clients=["android", "tv_embedded", "web_safari", "web"]))

    cookie_options = _ytdlp_options(use_cookies=True, player_clients=["web", "web_safari"])
    cookie_options["nocheckcertificate"] = True
    cookie_options["extract_flat"] = False
    attempts.append(cookie_options)

    web_options = _ytdlp_options(use_cookies=False, player_clients=["web", "web_safari", "tv_embedded"])
    web_options["nocheckcertificate"] = True
    web_options["extract_flat"] = False
    attempts.append(web_options)

    last_error: Exception | None = None
    for options in attempts:
        options["nocheckcertificate"] = True
        options["extract_flat"] = False
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as exc:
            last_error = exc
            msg = str(exc)
            if "cookies are no longer valid" in msg or "Sign in to confirm you’re not a bot" in msg:
                continue
            if "Requested format is not available" in msg or "format not available" in msg:
                fallback = options.copy()
                fallback.pop("format", None)
                fallback.pop("extractor_args", None)
                fallback["noplaylist"] = True
                with yt_dlp.YoutubeDL(fallback) as ydl:
                    return ydl.extract_info(url, download=False)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to extract video info")


def _instagram_follower_count(info: dict[str, Any]) -> int | None:
    username = info.get("uploader_id") or info.get("uploader") or info.get("channel")
    if not username:
        return None
    loader = instaloader.Instaloader(download_pictures=False, download_videos=False, download_comments=False, save_metadata=False, quiet=True)
    try:
        profile = instaloader.Profile.from_username(loader.context, str(username).lstrip("@"))
        return int(profile.followers)
    except Exception:
        return None


def _youtube_follower_count(info: dict[str, Any]) -> int | None:
    for key in ("channel_follower_count", "uploader_subscriber_count", "subscriber_count"):
        value = info.get(key)
        if value is not None:
            try:
                return int(value)
            except Exception:
                continue
    return None


def _build_segments(url: str, info: dict[str, Any]) -> list[TranscriptSegment]:
    platform = _extract_platform(url)
    if platform == "youtube":
        try:
            return fetch_youtube_transcript(url, info)
        except Exception:
            return fetch_fallback_transcript(url, info)
    return fetch_fallback_transcript(url, info)


def inspect_video(url: str, video_id: str, label: str, pair_id: str) -> tuple[VideoMetadata, list[TranscriptSegment], dict[str, Any]]:
    info = _extract_info(url)
    platform = _extract_platform(url)
    segments = _build_segments(url, info)
    transcript_text = segments_to_text(segments)
    raw_views = info.get("view_count") if info.get("view_count") is not None else info.get("play_count")
    views = None
    if raw_views is not None:
        try:
            views = int(raw_views)
        except Exception:
            views = None
    likes = int(info.get("like_count") or 0)
    comments = int(info.get("comment_count") or 0)
    if platform == "youtube":
        creator = str(info.get("channel") or info.get("uploader") or "Unknown creator")
        follower_count = _youtube_follower_count(info)
    else:
        creator = str(info.get("uploader") or info.get("channel") or "Unknown creator")
        follower_count = _instagram_follower_count(info)
    if platform == "instagram" and (views is None or views <= 0) and (likes > 0 or comments > 0):
        views = None

    engagement_rate = round(((likes + comments) / views * 100.0) if views else 0.0, 2)
    metadata = VideoMetadata(
        video_id=video_id,
        label=label,
        platform=platform,
        url=url,
        title=str(info.get("title") or "Untitled video"),
        creator=creator,
        follower_count=follower_count,
        views=views,
        likes=likes,
        comments=comments,
        hashtags=_extract_hashtags(info),
        upload_date=_format_upload_date(info),
        duration_seconds=int(info.get("duration") or 0) or None,
        engagement_rate=engagement_rate,
        transcript_preview=transcript_text[:500],
        hook_preview=first_seconds_preview(segments),
        chunk_count=0,
    )
    return metadata, segments, info
