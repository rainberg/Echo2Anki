"""
Test script for the Cohere + Whisper processing pipeline.

Usage:
    source /opt/anki-venv/bin/activate
    python /opt/anki-app/test_pipeline.py [audio_file_path]

If no audio file path is provided, downloads a test German audio sample.
"""

import logging
import sys
import os
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Add project to path
sys.path.insert(0, "/opt/anki-app")

from cohere_asr import CohereASR
from whisper_timestamps import WhisperTimestampExtractor
from align_and_cut import process_pipeline, split_into_sentences, align_text_to_timestamps


def get_test_audio():
    """Get a test German audio file."""
    # Check if a file was provided as argument
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        if os.path.exists(test_file):
            return test_file
        else:
            logger.error(f"Provided file does not exist: {test_file}")

    # Check common test locations
    for path in [
        "/tmp/test_audio_de.mp3",
        "/tmp/test_audio_de.wav",
        "/tmp/test_audio.mp3",
    ]:
        if os.path.exists(path):
            return path

    logger.error(
        "No test audio file found.\n"
        "Usage: python test_pipeline.py <path_to_german_audio_file>\n"
        "Or place a test file at /tmp/test_audio_de.mp3"
    )
    sys.exit(1)


def main():
    audio_path = get_test_audio()
    output_dir = "/tmp/test_clips"

    logger.info("=" * 60)
    logger.info("Cohere + Whisper Pipeline Test")
    logger.info("=" * 60)
    logger.info(f"Input audio: {audio_path}")
    logger.info(f"Output dir: {output_dir}")
    logger.info(f"File size: {os.path.getsize(audio_path) / 1024:.1f} KB")
    logger.info("")

    # Initialize models
    logger.info("Initializing models...")
    logger.info("  Loading Cohere ASR (this may take a while for first load)...")
    asr = CohereASR(device="cpu")

    logger.info("  Loading Whisper tiny...")
    whisper = WhisperTimestampExtractor(
        model_size="tiny",
        device="cpu",
        compute_type="int8",
    )
    logger.info("")

    # Run pipeline
    logger.info("Running pipeline...")
    segments, clip_paths = process_pipeline(
        audio_path=audio_path,
        asr_model=asr,
        whisper_extractor=whisper,
        output_dir=output_dir,
    )

    # Save results to JSON
    results = {
        "audio_file": audio_path,
        "total_sentences": len(segments),
        "total_clips": len(clip_paths),
        "segments": [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in segments],
    }
    json_path = os.path.join(output_dir, "transcription_result.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Results saved to {json_path}")

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("RESULTS SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total sentences: {len(segments)}")
    logger.info(f"Total clips: {len(clip_paths)}")

    print("\n--- Transcribed Sentences ---")
    for i, seg in enumerate(segments):
        print(f"{i+1:3d}. [{seg['start']:.1f}s - {seg['end']:.1f}s] {seg['text']}")

    print(f"\n--- Output Clips ({output_dir}) ---")
    for path in clip_paths:
        size_kb = os.path.getsize(path) / 1024
        print(f"  {path} ({size_kb:.1f} KB)")

    logger.info("Test completed successfully!")


if __name__ == "__main__":
    main()
