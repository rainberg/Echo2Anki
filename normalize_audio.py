from __future__ import annotations

import argparse

from audio_normalize import normalize_audio


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize audio for transcription.")
    parser.add_argument("--input", "-i", required=True, help="Input audio path.")
    parser.add_argument("--output", "-o", required=True, help="Output MP3 path.")
    parser.add_argument("--sample-rate", type=int, default=16000)
    parser.add_argument("--bitrate", default="96k")
    parser.add_argument("--mono", action="store_true", help="Kept for CLI compatibility; output is always mono.")
    parser.add_argument("--no-denoise", action="store_true")
    args = parser.parse_args()

    output = normalize_audio(
        args.input,
        output_path=args.output,
        sample_rate=args.sample_rate,
        bitrate=args.bitrate,
        denoise=not args.no_denoise,
    )
    print(output)


if __name__ == "__main__":
    main()
