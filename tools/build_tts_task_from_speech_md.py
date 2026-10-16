import asyncio
import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import edge_tts


SOURCE = Path(os.environ.get("SPEECH_TTS_SOURCE", ""))
ROOT = Path(os.environ.get("SPEECH_TTS_ROOT", "exports/speech_tts_task"))
TASK_ID = os.environ.get("SPEECH_TTS_TASK_ID", "speech_tts_task")
UPLOAD_NAME = os.environ.get("SPEECH_TTS_UPLOAD_NAME", "Sprechtext DE-ZH TTS")
VOICE = os.environ.get("SPEECH_TTS_VOICE", "de-DE-ConradNeural")
RATE = os.environ.get("SPEECH_TTS_RATE", "+0%")
SERVER_ROOT = os.environ.get("SPEECH_TTS_SERVER_ROOT", f"/var/lib/anki/tasks/{{user_id}}/{{task_id}}")

CLIPS = ROOT / "clips"
FULL_AUDIO = ROOT / "normalized.mp3"


def parse_source() -> list[dict]:
    if not SOURCE.exists():
        raise RuntimeError(f"Source file not found: {SOURCE}")

    raw = SOURCE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"## Folie\s+(\d+)\s+-\s+([^\n]+)\n\n"
        r"\*\*DE:\*\*\s*\n(.*?)\n\n"
        r"\*\*ZH:\*\*\s*\n(.*?)(?=\n---\n\n## Folie|\n---\s*\Z|\Z)",
        re.S,
    )
    items = []
    for match in pattern.finditer(raw):
        items.append(
            {
                "num": int(match.group(1)),
                "title": match.group(2).strip(),
                "de": re.sub(r"\s+", " ", match.group(3).strip()),
                "zh": re.sub(r"\s+", " ", match.group(4).strip()),
            }
        )
    if not items:
        raise RuntimeError("No Folie DE/ZH blocks were parsed.")
    return items


async def make_clip(item: dict) -> None:
    fname = CLIPS / f"clip_{item['num']:03d}.mp3"
    communicate = edge_tts.Communicate(item["de"], VOICE, rate=RATE)
    await communicate.save(str(fname))


async def make_clips(items: list[dict]) -> None:
    if CLIPS.exists():
        shutil.rmtree(CLIPS)
    CLIPS.mkdir(parents=True, exist_ok=True)
    for item in items:
        print(f"TTS {item['num']:02d}", flush=True)
        await make_clip(item)


def duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(proc.stdout.strip())


def build_full_audio(items: list[dict]) -> list[dict]:
    silence = ROOT / "silence_600ms.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            "0.6",
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(silence),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    concat_list = ROOT / "concat.txt"
    with concat_list.open("w", encoding="utf-8") as handle:
        for idx, item in enumerate(items):
            clip = (CLIPS / f"clip_{item['num']:03d}.mp3").resolve()
            handle.write(f"file '{clip.as_posix()}'\n")
            if idx != len(items) - 1:
                handle.write(f"file '{silence.resolve().as_posix()}'\n")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-ac",
            "1",
            "-ar",
            "44100",
            "-codec:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(FULL_AUDIO),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    segments = []
    current = 0.0
    for item in items:
        clip = CLIPS / f"clip_{item['num']:03d}.mp3"
        clip_duration = duration(clip)
        segments.append(
            {
                "start": round(current, 3),
                "end": round(current + clip_duration, 3),
                "text": f"Folie {item['num']:02d}: {item['title']} - {item['de']}",
            }
        )
        current += clip_duration + 0.6
    return segments


def write_manifest(items: list[dict], segments: list[dict]) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    manifest = {
        "task_id": TASK_ID,
        "upload_name": UPLOAD_NAME,
        "upload_key": f"manual:{TASK_ID}:edge-tts:{VOICE}:utf8",
        "created_at": now,
        "updated_at": now,
        "normalized_audio_path": f"{SERVER_ROOT}/normalized.mp3",
        "audio_dir": f"{SERVER_ROOT}/clips",
        "segments": segments,
        "translations": [item["zh"] for item in items],
        "favorites": list(range(len(items))),
        "push_excluded": [],
        "source_file": str(SOURCE),
        "tts_voice": VOICE,
    }
    (ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (ROOT / "source_items.json").write_text(
        json.dumps(items, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    items = parse_source()
    asyncio.run(make_clips(items))
    segments = build_full_audio(items)
    write_manifest(items, segments)
    summary = {
        "task_id": TASK_ID,
        "upload_name": UPLOAD_NAME,
        "voice": VOICE,
        "clips": len(items),
        "duration": round(duration(FULL_AUDIO), 3),
        "has_question_mark_in_de": any("?" in item["de"] or "?" in item["title"] for item in items),
        "has_question_mark_in_zh": any("?" in item["zh"] for item in items),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
