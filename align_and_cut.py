"""
Text alignment and audio cutting module.
Aligns Cohere transcription with Whisper word timestamps,
then cuts audio into sentence-level clips using pydub.
"""

import logging
import re
import os
import tempfile
from difflib import SequenceMatcher
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

logger = logging.getLogger(__name__)


def detect_speech_chunks(
    audio_path: str,
    min_silence_len: int = 600,
    silence_margin_db: int = 16,
    keep_silence: int = 250,
    min_chunk_ms: int = 5000,
    max_chunk_ms: int = 45000,
) -> list[dict]:
    """
    Detect non-silent audio regions and merge them into ASR-sized chunks.

    The chunks are only used for transcription progress/stability. Final card
    clips are still cut from the original audio after timestamp alignment.
    """
    audio = AudioSegment.from_file(audio_path)
    duration_ms = len(audio)
    if duration_ms == 0:
        return []

    # dBFS can be -inf for empty/silent files; use a conservative fallback.
    silence_thresh = -40 if audio.dBFS == float("-inf") else audio.dBFS - silence_margin_db
    ranges = detect_nonsilent(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_thresh,
        seek_step=10,
    )

    if not ranges:
        ranges = [[0, duration_ms]]

    expanded = []
    for start, end in ranges:
        start = max(0, start - keep_silence)
        end = min(duration_ms, end + keep_silence)
        if end > start:
            expanded.append([start, end])

    chunks = []
    cur_start = None
    cur_end = None

    for start, end in expanded:
        # Split very long continuous speech sections.
        if end - start > max_chunk_ms:
            if cur_start is not None:
                chunks.append([cur_start, cur_end])
                cur_start = cur_end = None
            split_start = start
            while split_start < end:
                split_end = min(end, split_start + max_chunk_ms)
                chunks.append([split_start, split_end])
                split_start = split_end
            continue

        if cur_start is None:
            cur_start, cur_end = start, end
            continue

        merged_duration = end - cur_start
        current_duration = cur_end - cur_start
        if merged_duration <= max_chunk_ms or current_duration < min_chunk_ms:
            cur_end = max(cur_end, end)
        else:
            chunks.append([cur_start, cur_end])
            cur_start, cur_end = start, end

    if cur_start is not None:
        chunks.append([cur_start, cur_end])

    # Avoid tiny trailing fragments when possible.
    merged = []
    for start, end in chunks:
        if merged and (end - start) < min_chunk_ms:
            merged[-1][1] = end
        else:
            merged.append([start, end])

    return [
        {"index": i + 1, "start": start / 1000, "end": end / 1000}
        for i, (start, end) in enumerate(merged)
        if end > start
    ]


def transcribe_silence_chunks(
    audio_path: str,
    asr_model,
    language: str = "de",
    progress_callback=None,
) -> list[dict]:
    """Transcribe an audio file chunk by chunk and keep chunk time ranges."""
    if progress_callback:
        progress_callback("detect_silence", 0, 0, "Detecting silence breaks...")

    chunks = detect_speech_chunks(audio_path)
    if not chunks:
        return []

    audio = AudioSegment.from_file(audio_path)
    transcription_chunks = []

    with tempfile.TemporaryDirectory(prefix="anki_asr_chunks_") as tmp_dir:
        for idx, chunk in enumerate(chunks, start=1):
            start_ms = int(chunk["start"] * 1000)
            end_ms = int(chunk["end"] * 1000)
            chunk_path = os.path.join(tmp_dir, f"asr_chunk_{idx:03d}.wav")
            audio[start_ms:end_ms].export(chunk_path, format="wav")

            message = (
                f"Transcribing chunk {idx}/{len(chunks)} "
                f"({chunk['start']:.1f}s-{chunk['end']:.1f}s)"
            )
            logger.info(message)
            if progress_callback:
                progress_callback("transcribe", idx, len(chunks), message)

            chunk_text = asr_model.transcribe(chunk_path, language=language)
            if chunk_text:
                transcription_chunks.append({
                    "index": idx,
                    "start": chunk["start"],
                    "end": chunk["end"],
                    "text": chunk_text.strip(),
                })

    return transcription_chunks


def transcribe_with_silence_chunks(
    audio_path: str,
    asr_model,
    language: str = "de",
    progress_callback=None,
) -> str:
    """Transcribe an audio file chunk by chunk using detected silence ranges."""
    chunks = transcribe_silence_chunks(
        audio_path,
        asr_model,
        language=language,
        progress_callback=progress_callback,
    )
    return "\n".join(chunk["text"] for chunk in chunks if chunk.get("text"))


def _normalize_alignment_word(word: str) -> str:
    """Normalize one word for Cohere/Whisper alignment."""
    return re.sub(r"^[^\wäöüÄÖÜß]+|[^\wäöüÄÖÜß]+$", "", word.lower())


def _words_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if len(left) <= 3 or len(right) <= 3:
        return False
    return SequenceMatcher(None, left, right).ratio() >= 0.78


def _find_sentence_start(
    sent_words: list[str],
    ts_words: list[str],
    search_from: int,
) -> int | None:
    """Find the likely start index of a sentence in a word timestamp window."""
    if not sent_words or not ts_words:
        return None

    n_ts = len(ts_words)
    match_len = min(4, len(sent_words), n_ts)
    if match_len == 0:
        return None

    best_idx = None
    best_score = 0.0
    for i in range(search_from, n_ts - match_len + 1):
        score = 0
        for j in range(match_len):
            if _words_similar(ts_words[i + j], sent_words[j]):
                score += 1

        score = score / match_len
        if score > best_score:
            best_idx = i
            best_score = score
            if score == 1:
                break

    return best_idx if best_idx is not None and best_score >= 0.65 else None


def _fallback_segments_for_chunk(chunk: dict) -> list[dict]:
    """Create approximate sentence ranges when Whisper has no words in a chunk."""
    sentences = split_into_sentences(chunk.get("text", ""))
    if not sentences:
        return []

    duration = max(0.2, chunk["end"] - chunk["start"])
    step = duration / len(sentences)
    segments = []
    for idx, sentence in enumerate(sentences):
        start = chunk["start"] + idx * step
        end = chunk["end"] if idx == len(sentences) - 1 else chunk["start"] + (idx + 1) * step
        segments.append({"text": sentence, "start": start, "end": end})
    return segments


def align_transcription_chunks_to_timestamps(
    transcription_chunks: list[dict],
    word_timestamps: list[dict],
    margin: float = 0.75,
) -> list[dict]:
    """
    Align each Cohere chunk only against the Whisper words inside that chunk.

    This prevents one bad sentence/word-count mismatch from shifting every
    later clip on long audio files.
    """
    aligned_segments = []
    used_until = 0.0

    for chunk in transcription_chunks:
        text = chunk.get("text", "").strip()
        if not text:
            continue

        window_start = max(0.0, chunk["start"] - margin)
        window_end = chunk["end"] + margin
        local_words = [
            word
            for word in word_timestamps
            if word["end"] >= window_start
            and word["start"] <= window_end
            and word["end"] > used_until - 0.05
        ]

        if local_words:
            chunk_segments = align_text_to_timestamps(text, local_words)
        else:
            logger.warning(
                "No Whisper words found for chunk %s (%.1fs-%.1fs); using approximate ranges",
                chunk.get("index"),
                chunk["start"],
                chunk["end"],
            )
            chunk_segments = _fallback_segments_for_chunk(chunk)

        for seg in chunk_segments:
            start = max(window_start, seg["start"])
            end = min(window_end, seg["end"])

            if aligned_segments and start < aligned_segments[-1]["end"]:
                start = aligned_segments[-1]["end"]
            if end <= start:
                end = min(window_end, start + 0.2)
            if end <= start:
                continue

            aligned_segments.append({
                "text": seg["text"],
                "start": start,
                "end": end,
            })
            used_until = max(used_until, end)

    return aligned_segments


def build_sentence_segments_from_whisper(
    transcript_segments: list[dict],
    word_timestamps: list[dict],
) -> list[dict]:
    """
    Build sentence-level clips directly from Whisper transcript records.

    Whisper provides both the text and word timestamps, so this avoids the
    cross-model Cohere-vs-Whisper alignment step entirely.
    """
    full_text = " ".join(
        segment.get("text", "").strip()
        for segment in transcript_segments
        if segment.get("text", "").strip()
    )

    if word_timestamps:
        return align_text_to_timestamps(full_text, word_timestamps)

    logger.warning("Whisper returned no word timestamps; falling back to segment ranges")
    fallback_segments = []
    for segment in transcript_segments:
        sentences = split_into_sentences(segment.get("text", ""))
        if not sentences:
            continue

        duration = max(0.2, segment["end"] - segment["start"])
        step = duration / len(sentences)
        for idx, sentence in enumerate(sentences):
            start = segment["start"] + idx * step
            end = segment["end"] if idx == len(sentences) - 1 else segment["start"] + (idx + 1) * step
            fallback_segments.append({"text": sentence, "start": start, "end": end})

    return fallback_segments


def split_into_sentences(text: str) -> list[str]:
    """
    Split German text into sentences.
    Handles: . ! ? as sentence boundaries,
    but avoids splitting on abbreviations like Dr., Prof., etc.
    """
    # Common German abbreviations that end with period
    abbreviations = r"\b(?:Dr|Prof|Dipl|Ing|Mag|Nr|ca|z\.B|d\.h|usw|etc|ggf|bzw|evtl|inkl|exkl|od|vgl|Abb|Abs|Kap|S|Tel|Fax|Max|Min|Std|Sek|Mrz|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez|Jan|Feb)\."
    
    # Temporarily replace abbreviation dots
    temp_placeholder = "__ABBR__"
    text_marked = re.sub(abbreviations, lambda m: m.group(0).replace(".", temp_placeholder), text)
    
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?])\s+', text_marked)
    
    # Restore abbreviation dots
    sentences = [s.replace(temp_placeholder, ".").strip() for s in sentences]
    
    # Filter empty
    return [s for s in sentences if s]


def align_text_to_timestamps(
    text: str,
    word_timestamps: list[dict],
) -> list[dict]:
    """
    Align Cohere transcription text with Whisper word timestamps.

    Strategy:
    - Split Cohere text into sentences
    - For each sentence, find the corresponding words in the timestamp list
    - Match by approximate word count and text overlap

    Returns:
        List of dicts: [{'text': str, 'start': float, 'end': float}, ...]
    """
    sentences = split_into_sentences(text)
    if not sentences:
        logger.warning("No sentences found in transcription")
        return []

    # Normalize timestamps text for matching
    ts_words = [_normalize_alignment_word(w["word"]) for w in word_timestamps]
    ts_starts = [w["start"] for w in word_timestamps]
    ts_ends = [w["end"] for w in word_timestamps]

    n_ts = len(ts_words)

    sentence_words = []
    for sentence in sentences:
        sent_words = [_normalize_alignment_word(w) for w in sentence.split()]
        sentence_words.append([w for w in sent_words if w])

    # Find sentence starts first. The next sentence's start gives a stronger
    # boundary than Cohere's word count when Whisper tokenization differs.
    starts = []
    search_from = 0
    for sent_words in sentence_words:
        if not sent_words:
            starts.append(None)
            continue

        start_idx = _find_sentence_start(sent_words, ts_words, search_from)
        if start_idx is None:
            start_idx = search_from

        starts.append(start_idx)
        search_from = min(start_idx + 1, n_ts)

    aligned = []
    for idx, sentence in enumerate(sentences):
        sent_words = sentence_words[idx]
        if not sent_words:
            continue

        start_idx = starts[idx]
        if start_idx is None:
            continue

        next_start = None
        for future_start in starts[idx + 1:]:
            if future_start is not None and future_start > start_idx:
                next_start = future_start
                break

        word_count = len(sent_words)
        end_idx = min(next_start, n_ts) if next_start is not None else min(start_idx + word_count, n_ts)

        if start_idx < n_ts and end_idx > start_idx:
            aligned.append({
                "text": sentence,
                "start": ts_starts[start_idx],
                "end": ts_ends[end_idx - 1],
            })
        else:
            # Can't align this sentence
            aligned.append({
                "text": sentence,
                "start": ts_starts[-1] if ts_starts else 0,
                "end": ts_ends[-1] if ts_ends else 0,
            })

    return aligned


def cut_audio_clips(
    audio_path: str,
    segments: list[dict],
    output_dir: str = "/tmp/test_clips",
) -> list[str]:
    """
    Cut audio into clips based on aligned segments.

    Args:
        audio_path: Path to source audio file
        segments: List of dicts with 'text', 'start', 'end'
        output_dir: Directory to save clips

    Returns:
        List of paths to generated clip files
    """
    os.makedirs(output_dir, exist_ok=True)

    # Load audio with pydub
    audio = AudioSegment.from_file(audio_path)
    duration_ms = len(audio)

    clip_paths = []
    for idx, seg in enumerate(segments):
        # Convert seconds to milliseconds
        start_ms = int(seg["start"] * 1000)
        end_ms = int(seg["end"] * 1000)

        # Clamp to audio duration
        start_ms = max(0, start_ms)
        end_ms = min(end_ms, duration_ms)

        # Ensure minimum clip length (100ms)
        if end_ms - start_ms < 100:
            end_ms = min(start_ms + 200, duration_ms)

        # Add small padding (50ms)
        pad = 50
        start_ms = max(0, start_ms - pad)
        end_ms = min(duration_ms, end_ms + pad)

        # Cut and export
        clip = audio[start_ms:end_ms]
        clip_path = os.path.join(output_dir, f"clip_{idx+1:03d}.mp3")
        clip.export(clip_path, format="mp3", bitrate="64k")
        clip_paths.append(clip_path)

        logger.info(f"  Clip {idx+1:03d}: {seg['start']:.1f}s-{seg['end']:.1f}s -> {clip_path}")
        logger.info(f"    Text: {seg['text'][:80]}...")

    return clip_paths


def process_pipeline(
    audio_path: str,
    asr_model=None,
    whisper_extractor=None,
    output_dir: str = "/tmp/test_clips",
    progress_callback=None,
) -> tuple[list[dict], list[str]]:
    """
    Full pipeline: Whisper transcription/timestamps -> sentence split -> cut.

    Args:
        audio_path: Path to input audio file
        asr_model: Deprecated; kept for compatibility with older callers
        whisper_extractor: WhisperTimestampExtractor instance
        output_dir: Directory to save clips

    Returns:
        (segments, clip_paths)
    """
    logger.info(f"Processing: {audio_path}")
    if whisper_extractor is None:
        raise ValueError("whisper_extractor is required")

    # Step 1: Whisper transcription and timestamp extraction
    logger.info("Step 1/3: Whisper transcription with word timestamps...")
    if progress_callback:
        progress_callback("whisper", 0, 0, "Transcribing with Whisper...")
    transcript_segments, word_timestamps = whisper_extractor.transcribe_with_segments(
        audio_path, language="de"
    )
    logger.info(
        "Whisper returned %s transcript segments and %s word timestamps",
        len(transcript_segments),
        len(word_timestamps),
    )

    # Step 2: Split Whisper text into sentence-level timestamp ranges
    logger.info("Step 2/3: Building sentence segments from Whisper records...")
    if progress_callback:
        progress_callback("align", 0, 0, "Splitting Whisper transcript into sentences...")
    segments = build_sentence_segments_from_whisper(
        transcript_segments,
        word_timestamps,
    )
    logger.info(f"Found {len(segments)} sentence segments")

    # Step 3: Cut audio into clips
    logger.info("Step 3/3: Cutting audio clips...")
    if progress_callback:
        progress_callback("cut", 0, 0, "Cutting sentence audio clips...")
    clip_paths = cut_audio_clips(audio_path, segments, output_dir)

    logger.info(f"Done! Generated {len(clip_paths)} clips in {output_dir}")
    return segments, clip_paths
