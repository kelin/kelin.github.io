from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS_DIR = ROOT / ".blog_pipeline" / "transcripts"
AUDIO_VIDEO_SOURCE_TYPES = {"podcast", "video", "official-content"}
_MODEL_CACHE: dict[tuple[str, str], object] = {}


def is_audio_video_source(meta: dict) -> bool:
    return (meta.get("source_type") or "").strip().lower() in AUDIO_VIDEO_SOURCE_TYPES


def normalize_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def is_text_too_thin(text: str, min_chars: int) -> bool:
    compact = re.sub(r"\s+", " ", text or "").strip()
    return len(compact) < max(200, int(min_chars))


def is_js_shell_text(text: str) -> bool:
    t = (text or "").lower()
    return (
        "this site requires javascript" in t
        or "please turn on javascript" in t
        or "enable javascript" in t
    )


def should_attempt_whisper(meta: dict, page_text: str, min_chars: int) -> bool:
    if not is_audio_video_source(meta):
        return False
    return is_js_shell_text(page_text) or is_text_too_thin(page_text, min_chars)


def resolve_media_url(meta: dict) -> str:
    for key in ("media_url", "audio_url", "enclosure_url"):
        value = (meta.get(key) or "").strip()
        if value:
            return value

    page_url = (meta.get("url") or "").strip()
    if not page_url:
        return ""

    host = (urlparse(page_url).netloc or "").lower()
    if any(x in host for x in ("youtube.com", "youtu.be", "bilibili.com", "b23.tv")):
        return page_url
    return ""


def _cache_key(media_url: str, model_name: str, language: str | None, compute_type: str) -> str:
    raw = json.dumps(
        {
            "media_url": media_url,
            "model": model_name,
            "language": language or "",
            "compute_type": compute_type,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _cache_paths(media_url: str, model_name: str, language: str | None, compute_type: str) -> tuple[Path, Path]:
    key = _cache_key(media_url, model_name, language, compute_type)
    return TRANSCRIPTS_DIR / f"{key}.txt", TRANSCRIPTS_DIR / f"{key}.json"


def _has_bin(name: str) -> bool:
    return shutil.which(name) is not None


def _is_media_page_url(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower()
    return any(x in host for x in ("youtube.com", "youtu.be", "bilibili.com", "b23.tv"))


def _looks_like_direct_media(url: str, meta: dict) -> bool:
    media_type = (meta.get("media_type") or "").lower()
    if media_type.startswith("audio/") or media_type.startswith("video/"):
        return True

    path = (urlparse(url).path or "").lower()
    return any(path.endswith(ext) for ext in (".mp3", ".m4a", ".aac", ".wav", ".mp4", ".m4v", ".webm", ".ogg", ".opus", ".mpga"))


def _download_direct_media_to_wav(source_url: str, out_wav: Path) -> Path:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        source_url,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(out_wav),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"ffmpeg download failed: {(proc.stderr or '').strip()[-300:]}")
    return out_wav


def _download_page_media(source_url: str, work_dir: Path) -> Path:
    if not _has_bin("yt-dlp"):
        raise RuntimeError("yt-dlp is not installed")

    template = work_dir / "media.%(ext)s"
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "-f",
        "bestaudio/best",
        "-o",
        str(template),
        source_url,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {(proc.stderr or proc.stdout or '').strip()[-300:]}")

    files = sorted(work_dir.glob("media.*"))
    if not files:
        raise RuntimeError("yt-dlp finished but no media file was found")
    return files[0]


def _convert_media_to_wav(src_path: Path, out_wav: Path) -> Path:
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-y",
        "-i",
        str(src_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(out_wav),
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0 or not out_wav.exists():
        raise RuntimeError(f"ffmpeg convert failed: {(proc.stderr or '').strip()[-300:]}")
    return out_wav


def _get_whisper_model(model_name: str, compute_type: str):
    key = (model_name, compute_type)
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]

    from faster_whisper import WhisperModel  # type: ignore

    model = WhisperModel(model_name, device="cpu", compute_type=compute_type)
    _MODEL_CACHE[key] = model
    return model


def _format_ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    hh, rem = divmod(ms, 3600_000)
    mm, rem = divmod(rem, 60_000)
    ss, ms = divmod(rem, 1000)
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"


def transcribe_media_url(
    media_url: str,
    *,
    meta: dict,
    model_name: str,
    language: str | None,
    compute_type: str,
    max_chars: int,
) -> tuple[str | None, str]:
    media_url = (media_url or "").strip()
    if not media_url:
        return None, "missing media url"

    cached_txt, cached_meta = _cache_paths(media_url, model_name, language, compute_type)
    if cached_txt.exists():
        return cached_txt.read_text(encoding="utf-8", errors="ignore"), "cache-hit"

    if not _has_bin("ffmpeg"):
        return None, "ffmpeg unavailable"

    try:
        import faster_whisper  # type: ignore  # noqa: F401
    except Exception:
        return None, "faster-whisper unavailable"

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="blog-whisper-") as tmp:
            tmp_dir = Path(tmp)
            wav_path = tmp_dir / "input.wav"

            if _looks_like_direct_media(media_url, meta):
                prepared_audio = _download_direct_media_to_wav(media_url, wav_path)
            elif _is_media_page_url(media_url):
                downloaded_media = _download_page_media(media_url, tmp_dir)
                prepared_audio = _convert_media_to_wav(downloaded_media, wav_path)
            else:
                return None, "no supported media downloader for this url"

            model = _get_whisper_model(model_name, compute_type)
            segments, _info = model.transcribe(
                str(prepared_audio),
                language=(language or None),
                vad_filter=True,
            )

            lines: list[str] = []
            for seg in segments:
                text = normalize_text(getattr(seg, "text", ""))
                if not text:
                    continue
                start = _format_ts(float(getattr(seg, "start", 0.0)))
                end = _format_ts(float(getattr(seg, "end", 0.0)))
                lines.append(f"[{start} - {end}] {text}")

            transcript = "\n".join(lines).strip()
            if not transcript:
                return None, "whisper produced empty transcript"

            transcript = transcript[:max_chars]
            cached_txt.write_text(transcript, encoding="utf-8")
            cached_meta.write_text(
                json.dumps(
                    {
                        "media_url": media_url,
                        "page_url": meta.get("url", ""),
                        "title": meta.get("title", ""),
                        "source": meta.get("program", ""),
                        "model": model_name,
                        "language": language or "",
                        "compute_type": compute_type,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            return transcript, "whisper"
    except Exception as exc:
        return None, str(exc)


def build_transcript_source_text(meta: dict, transcript_text: str, page_text: str) -> str:
    parts = [
        "[内容来源说明] 以下正文优先基于自动转写生成。请注意自动转写可能存在少量人名、术语或时间点误差。",
        "[自动转写稿]",
        normalize_text(transcript_text),
    ]

    fallback_notes = normalize_text(page_text)
    if fallback_notes:
        parts.extend(["[页面摘要 / Show Notes 兜底参考]", fallback_notes])

    return "\n\n".join([x for x in parts if x]).strip()
