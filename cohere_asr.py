"""
Cohere Transcribe ASR module
Loads CohereLabs/cohere-transcribe-03-2026 model for German speech recognition.
CPU inference with transformers.
"""

import logging
import torch
import librosa
from transformers import (
    AutoProcessor,
    AutoModelForSpeechSeq2Seq,
)

logger = logging.getLogger(__name__)

MODEL_ID = "CohereLabs/cohere-transcribe-03-2026"
SAMPLE_RATE = 16000

# Language prompt template for Cohere ASR
# Supported: en, fr, de, es, it, pt, nl, pl, el, ar, ja, zh, vi, ko
LANGUAGE_PROMPT = {
    "de": "<|startoftranscript|><|de|><|pnc|><|notimestamp|><|nodiarize|><|noitn|><|emo:undefined|>",
    "en": "<|startoftranscript|><|en|><|pnc|><|notimestamp|><|nodiarize|><|noitn|><|emo:undefined|>",
}


class CohereASR:
    """Cohere Transcribe ASR model wrapper for CPU inference."""

    def __init__(self, device: str = "cpu", model_id: str = MODEL_ID, chunk_seconds: int = 30):
        self.device = torch.device(device)
        self.chunk_seconds = chunk_seconds
        logger.info(f"Loading Cohere ASR model: {model_id} on {device}")

        self.processor = AutoProcessor.from_pretrained(
            model_id,
            trust_remote_code=True,
        )
        self.model = AutoModelForSpeechSeq2Seq.from_pretrained(
            model_id,
            trust_remote_code=True,
            torch_dtype=torch.float32,
        ).to(self.device)
        self.model.eval()

        self.sample_rate = SAMPLE_RATE
        logger.info("Cohere ASR model loaded successfully")

    def transcribe(
        self,
        audio_path: str,
        language: str = "de",
        return_timestamps: bool = False,
    ) -> str:
        """
        Transcribe audio file to text.
        Uses chunked processing (30-second chunks) to avoid OOM on CPU.
        """
        # Load and resample audio
        audio, sr = librosa.load(audio_path, sr=self.sample_rate, mono=True)

        prompt = LANGUAGE_PROMPT.get(language, LANGUAGE_PROMPT["en"])
        total_duration = len(audio) / self.sample_rate

        # Process in chunks to avoid OOM
        chunk_duration = self.chunk_seconds  # seconds
        chunk_samples = chunk_duration * self.sample_rate
        all_transcriptions = []

        for start_sample in range(0, len(audio), chunk_samples):
            chunk = audio[start_sample:start_sample + chunk_samples]
            chunk_sec = len(chunk) / self.sample_rate

            # Skip very short trailing chunks
            if chunk_sec < 1.0:
                break

            inputs = self.processor(
                chunk,
                sampling_rate=self.sample_rate,
                text=prompt,
                return_tensors="pt",
            ).to(self.device)

            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=448,
                )

            chunk_text = self.processor.batch_decode(
                generated_ids,
                skip_special_tokens=True,
            )[0].strip()

            # Remove prompt prefix if present
            for lang_code in LANGUAGE_PROMPT.values():
                if chunk_text.startswith(lang_code):
                    chunk_text = chunk_text[len(lang_code):].strip()
                    break

            if chunk_text:
                all_transcriptions.append(chunk_text)

            logger.debug(f"  Chunk {len(all_transcriptions)}/{int(total_duration/chunk_duration)+1}: "
                         f"'{chunk_text[:60]}...' ({chunk_sec:.1f}s)")
            # Clean up chunk tensors
            del inputs, generated_ids, chunk
            import gc; gc.collect()

        return "\n".join(all_transcriptions)

    def transcribe_file(self, audio_path: str, language: str = "de") -> str:
        """Convenience wrapper for transcribe()."""
        return self.transcribe(audio_path, language=language)
