"""
Audio normalization utilities for the Anki audio pipeline.

The normalized output is optimized for speech transcription:
- MP3
- mono
- 16 kHz
- 96 kbps
- optional light denoise
- loudness normalization
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def normalize_audio(
    input_path: str,
    output_path: str | None = None,
    sample_rate: int = 16000,
    bitrate: str = "96k",
    denoise: bool = True,
) -> str:
    """
    Normalize uploaded audio to a speech-friendly MP3.

    Args:
        input_path: Source audio path.
        output_path: Optional target .mp3 path.
        sample_rate: Target sample rate. Defaults to 16 kHz.
        bitrate: Target MP3 bitrate. Defaults to 96 kbps.
        denoise: Apply a light afftdn denoise filter before loudness normalization.

    Returns:
        The normalized output path.
    """
    source = Path(input_path)
    if output_path is None:
        output_path = str(source.with_suffix("")) + ".normalized.mp3"

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    filters = []
    if denoise:
        # Conservative broadband denoise. Stronger denoise can hurt consonants.
        filters.append("afftdn=nf=-25")
    filters.append("loudnorm=I=-18:TP=-2:LRA=11")

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-af",
        ",".join(filters),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(target),
    ]
    subprocess.run(command, check=True)
    return str(target)


def describe_audio(audio_path: str) -> dict:
    """Return basic audio metadata using ffprobe."""
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,channels,sample_rate,bit_rate",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1:nokey=0",
        audio_path,
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    info = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            info[key] = value
    return info
