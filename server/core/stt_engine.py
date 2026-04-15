"""
Speech-to-Text Engine — Offline using faster-whisper.
Processes audio chunks and returns transcriptions.
"""

import logging
import io
import struct
import numpy as np
from typing import Optional

logger = logging.getLogger("Jarvis.STT")


class STTEngine:
    """Offline speech-to-text using faster-whisper."""

    def __init__(self, config: dict):
        self.model_size = config.get("model", "tiny.en")
        self.device = config.get("device", "cpu")
        self.compute_type = config.get("compute_type", "int8")
        self.beam_size = config.get("beam_size", 1)
        self.language = config.get("language", "en")
        self.vad_filter = config.get("vad_filter", True)
        self.vad_threshold = config.get("vad_threshold", 0.5)
        self._model = None
        self._load_model()

    def _load_model(self):
        try:
            from faster_whisper import WhisperModel

            logger.info(f"Loading Whisper model: {self.model_size} on {self.device}")
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Whisper model loaded successfully")
        except ImportError:
            logger.warning(
                "faster-whisper not installed. "
                "Install with: pip install faster-whisper"
            )
            self._model = None
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self._model = None

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> Optional[str]:
        """
        Transcribe raw PCM audio bytes (int16, mono) to text.
        Returns the transcribed text or None if failed.
        """
        if self._model is None:
            logger.error("STT model not loaded")
            return None

        try:
            # Convert raw PCM int16 bytes to float32 numpy array
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            audio_np /= 32768.0  # Normalize to [-1, 1]

            if len(audio_np) == 0:
                return None

            # Run transcription
            segments, info = self._model.transcribe(
                audio_np,
                beam_size=self.beam_size,
                language=self.language,
                vad_filter=self.vad_filter,
                vad_parameters={"threshold": self.vad_threshold},
            )

            # Collect all segments
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            full_text = " ".join(text_parts).strip()

            if full_text:
                logger.info(f"Transcribed: '{full_text}'")
                return full_text
            else:
                logger.info("No speech detected in audio")
                return None

        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            return None

    def transcribe_streaming(self, audio_bytes: bytes, sample_rate: int = 16000):
        """
        Generator that yields partial transcriptions for streaming display.
        """
        if self._model is None:
            return

        try:
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            audio_np /= 32768.0

            if len(audio_np) == 0:
                return

            segments, info = self._model.transcribe(
                audio_np,
                beam_size=self.beam_size,
                language=self.language,
                vad_filter=self.vad_filter,
                vad_parameters={"threshold": self.vad_threshold},
            )

            for segment in segments:
                text = segment.text.strip()
                if text:
                    yield text

        except Exception as e:
            logger.error(f"Streaming transcription error: {e}", exc_info=True)

    @property
    def is_available(self) -> bool:
        return self._model is not None
