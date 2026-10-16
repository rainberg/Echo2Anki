"""
Whisper timestamp extraction module
Uses faster-whisper to extract transcript text and word-level timestamps.
"""

import logging
import numpy as np
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

WHISPER_MODEL_SIZE = "small"
WHISPER_MODEL_DIR = None  # Uses default HF cache


class WhisperTimestampExtractor:
    """Extract word-level timestamps using faster-whisper."""

    def __init__(
        self,
        model_size: str = WHISPER_MODEL_SIZE,
        device: str = "cpu",
        compute_type: str = "int8",
    ):
        logger.info(f"Loading faster-whisper {model_size} model on {device} ({compute_type})")
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=WHISPER_MODEL_DIR,
        )
        logger.info("Whisper model loaded successfully")

    def extract_word_timestamps(
        self,
        audio_path: str,
        language: str = "de",
    ) -> list[dict]:
        """
        Extract word-level timestamps from audio file.

        Returns:
            List of dicts: [{'word': str, 'start': float, 'end': float}, ...]
        """
        _segments, word_timestamps = self.transcribe_with_segments(
            audio_path,
            language=language,
        )
        return word_timestamps

    def transcribe_with_segments(
        self,
        audio_path: str,
        language: str = "de",
    ) -> tuple[list[dict], list[dict]]:
        """
        Transcribe audio with Whisper and return both text segments and words.

        The returned text and timestamps come from the same model pass, so the
        sentence clips can be cut without aligning a second ASR transcript.
        """
        segments, info = self.model.transcribe(
            audio_path,
            language=language,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )

        transcript_segments = []
        word_timestamps = []
        for segment in segments:
            segment_words = []
            if segment.words:
                for word_info in segment.words:
                    word = {
                        "word": word_info.word.strip(),
                        "start": word_info.start,
                        "end": word_info.end,
                    }
                    segment_words.append(word)
                    word_timestamps.append(word)

            text = (segment.text or "").strip()
            if text:
                transcript_segments.append({
                    "text": text,
                    "start": segment.start,
                    "end": segment.end,
                    "words": segment_words,
                })

        logger.info(
            f"Extracted {len(transcript_segments)} transcript segments and "
            f"{len(word_timestamps)} word timestamps "
            f"(language: {info.language}, probability: {info.language_probability:.2f})"
        )
        return transcript_segments, word_timestamps
