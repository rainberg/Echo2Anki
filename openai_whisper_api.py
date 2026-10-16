"""
OpenAI Whisper API adapter.

Provides the same transcribe_with_segments() shape as WhisperTimestampExtractor
so the Streamlit pipeline can switch between local faster-whisper and OpenAI's
whisper-1 transcription API.
"""

import os
from pathlib import Path

import requests


class OpenAIWhisperAPI:
    """Transcribe audio through OpenAI's transcription API."""

    api_url = "https://api.openai.com/v1/audio/transcriptions"
    max_file_bytes = 25 * 1024 * 1024

    def __init__(self, api_key: str | None = None, model: str = "whisper-1"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.model = model
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not configured")

    def transcribe_with_segments(
        self,
        audio_path: str,
        language: str = "de",
    ) -> tuple[list[dict], list[dict]]:
        path = Path(audio_path)
        size = path.stat().st_size
        if size > self.max_file_bytes:
            mb = size / 1024 / 1024
            raise ValueError(
                f"OpenAI Whisper API supports files up to 25 MB; this file is {mb:.1f} MB"
            )

        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = [
            ("model", self.model),
            ("language", language),
            ("response_format", "verbose_json"),
            ("timestamp_granularities[]", "word"),
            ("timestamp_granularities[]", "segment"),
        ]

        with path.open("rb") as audio_file:
            files = {"file": (path.name, audio_file, "audio/mpeg")}
            response = requests.post(
                self.api_url,
                headers=headers,
                data=data,
                files=files,
                timeout=600,
            )

        if response.status_code >= 400:
            raise RuntimeError(f"OpenAI transcription failed: {response.text[:1000]}")

        payload = response.json()
        transcript_segments = []
        for segment in payload.get("segments", []) or []:
            text = (segment.get("text") or "").strip()
            if text:
                transcript_segments.append({
                    "text": text,
                    "start": float(segment.get("start", 0.0)),
                    "end": float(segment.get("end", 0.0)),
                    "words": [],
                })

        word_timestamps = []
        for word in payload.get("words", []) or []:
            text = (word.get("word") or "").strip()
            if text:
                word_timestamps.append({
                    "word": text,
                    "start": float(word.get("start", 0.0)),
                    "end": float(word.get("end", 0.0)),
                })

        if not transcript_segments and payload.get("text"):
            transcript_segments.append({
                "text": payload["text"].strip(),
                "start": 0.0,
                "end": float(payload.get("duration", 0.0)),
                "words": word_timestamps,
            })

        return transcript_segments, word_timestamps
