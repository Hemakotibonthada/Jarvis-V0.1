"""
TTS Engine — Multi-backend text-to-speech with cross-platform fallbacks.
Priority: Piper TTS (offline) → edge-tts → macOS 'say' / Windows SAPI → silent
"""

import asyncio
import io
import logging
import platform
import struct
import subprocess
import wave
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("Jarvis.TTS")


class TTSEngine:
    """Cross-platform TTS with automatic fallback chain."""

    def __init__(self, config: dict):
        self.model_name = config.get("model", "en_US-lessac-medium")
        self.speaker_id = config.get("speaker_id", 0)
        self.length_scale = config.get("length_scale", 1.0)
        self.noise_scale = config.get("noise_scale", 0.667)
        self.noise_w = config.get("noise_w", 0.8)
        self.sentence_silence = config.get("sentence_silence", 0.3)
        self.output_sample_rate = config.get("output_sample_rate", 22050)
        self._platform = platform.system()
        self._backend = "none"
        self._piper_model_path: Optional[Path] = None
        self._detect_backend()

    def _detect_backend(self):
        """Detect the best available TTS backend."""
        # 1. Try Piper TTS (best quality, fully offline)
        try:
            import piper
            models_dir = Path(__file__).parent.parent / "models" / "tts"
            models_dir.mkdir(parents=True, exist_ok=True)
            model_files = list(models_dir.glob(f"{self.model_name}*.onnx"))
            if model_files:
                self._piper_model_path = model_files[0]
                self._backend = "piper"
                logger.info(f"TTS backend: Piper ({self._piper_model_path.name})")
                return
        except ImportError:
            pass

        # 2. Try piper CLI
        try:
            result = subprocess.run(
                ["piper", "--version"], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                self._backend = "piper_cli"
                logger.info("TTS backend: Piper CLI")
                return
        except (FileNotFoundError, Exception):
            pass

        # 3. macOS 'say' command (built-in, offline, decent quality)
        if self._platform == "Darwin":
            self._backend = "macos_say"
            logger.info("TTS backend: macOS 'say' (built-in)")
            return

        # 4. Windows SAPI via PowerShell (built-in, offline)
        if self._platform == "Windows":
            self._backend = "windows_sapi"
            logger.info("TTS backend: Windows SAPI (built-in)")
            return

        # 5. Linux espeak fallback (offline)
        if self._platform == "Linux":
            try:
                subprocess.run(["espeak", "--version"], capture_output=True, timeout=5)
                self._backend = "espeak"
                logger.info("TTS backend: espeak")
                return
            except (FileNotFoundError, Exception):
                pass

        # 6. Try edge-tts (needs internet, high quality, last resort)
        try:
            import edge_tts
            self._backend = "edge_tts"
            logger.info("TTS backend: edge-tts (requires internet)")
            return
        except ImportError:
            pass

        logger.warning("No TTS backend available! Audio responses will be silent.")

    async def synthesize(self, text: str) -> Optional[bytes]:
        """Convert text to raw PCM audio bytes (int16, mono)."""
        if not text or not text.strip():
            return None
        text = text.strip()

        try:
            if self._backend == "piper":
                return await self._synthesize_piper(text)
            elif self._backend == "piper_cli":
                return await self._synthesize_piper_cli(text)
            elif self._backend == "edge_tts":
                return await self._synthesize_edge_tts(text)
            elif self._backend == "macos_say":
                return await self._synthesize_macos(text)
            elif self._backend == "windows_sapi":
                return await self._synthesize_windows(text)
            elif self._backend == "espeak":
                return await self._synthesize_espeak(text)
        except Exception as e:
            logger.error(f"TTS synthesis error ({self._backend}): {e}", exc_info=True)

        return None

    async def _synthesize_piper(self, text: str) -> Optional[bytes]:
        """Synthesize using piper-tts Python library."""
        import piper
        loop = asyncio.get_event_loop()

        def _do_synthesis():
            voice = piper.PiperVoice.load(
                str(self._piper_model_path),
                config_path=str(self._piper_model_path).replace(".onnx", ".onnx.json"),
            )
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wav_file:
                voice.synthesize(
                    text, wav_file,
                    speaker_id=self.speaker_id,
                    length_scale=self.length_scale,
                    noise_scale=self.noise_scale,
                    noise_w=self.noise_w,
                    sentence_silence=self.sentence_silence,
                )
            wav_buffer.seek(0)
            with wave.open(wav_buffer, "rb") as wav_file:
                return wav_file.readframes(wav_file.getnframes())

        audio = await loop.run_in_executor(None, _do_synthesis)
        logger.debug(f"Piper: {len(text)} chars -> {len(audio)} bytes")
        return audio

    async def _synthesize_piper_cli(self, text: str) -> Optional[bytes]:
        """Synthesize using piper CLI tool."""
        process = await asyncio.create_subprocess_exec(
            "piper", "--model", self.model_name, "--output-raw",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=text.encode("utf-8"))
        if process.returncode == 0 and stdout:
            return stdout
        logger.error(f"Piper CLI: {stderr.decode()}")
        return None

    async def _synthesize_edge_tts(self, text: str) -> Optional[bytes]:
        """Synthesize using edge-tts (Microsoft online TTS, outputs MP3)."""
        import edge_tts
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
            await communicate.save(tmp_path)
            return self._mp3_to_pcm(tmp_path)
        except Exception as e:
            logger.error(f"edge-tts error: {e}")
            return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def _synthesize_macos(self, text: str) -> Optional[bytes]:
        """Synthesize using macOS built-in 'say' command."""
        with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            process = await asyncio.create_subprocess_exec(
                "say", "-v", "Samantha", "-o", tmp_path, "--data-format=LEI16@22050",
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            if process.returncode == 0:
                return self._aiff_to_pcm(tmp_path)
        except Exception as e:
            logger.error(f"macOS say error: {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return None

    async def _synthesize_windows(self, text: str) -> Optional[bytes]:
        """Synthesize using Windows SAPI via PowerShell script."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        # Write a PowerShell script to avoid escaping issues
        ps_script_path = tmp_path + ".ps1"
        # Escape text for PowerShell string (double single quotes)
        safe_text = text.replace("'", "''")
        ps_script = (
            "Add-Type -AssemblyName System.Speech\n"
            "$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            f"$synth.SetOutputToWaveFile('{tmp_path}')\n"
            f"$synth.Speak('{safe_text}')\n"
            "$synth.Dispose()\n"
        )

        try:
            Path(ps_script_path).write_text(ps_script, encoding="utf-8")

            process = await asyncio.create_subprocess_exec(
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", ps_script_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(process.communicate(), timeout=30)

            if process.returncode == 0 and Path(tmp_path).exists():
                pcm = self._wav_to_pcm(tmp_path)
                if pcm:
                    logger.debug(f"SAPI: {len(text)} chars -> {len(pcm)} bytes")
                    return pcm
                else:
                    logger.error("SAPI: WAV produced but PCM extraction failed")
            else:
                logger.error(f"SAPI: PowerShell returned {process.returncode}")
        except asyncio.TimeoutError:
            logger.error("Windows SAPI timed out")
        except Exception as e:
            logger.error(f"Windows SAPI error: {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
            Path(ps_script_path).unlink(missing_ok=True)
        return None

    async def _synthesize_espeak(self, text: str) -> Optional[bytes]:
        """Synthesize using espeak on Linux."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            process = await asyncio.create_subprocess_exec(
                "espeak", "-w", tmp_path, text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()

            if process.returncode == 0:
                return self._wav_to_pcm(tmp_path)
        except Exception as e:
            logger.error(f"espeak error: {e}")
        finally:
            Path(tmp_path).unlink(missing_ok=True)
        return None

    def _mp3_to_pcm(self, mp3_path: str) -> Optional[bytes]:
        """Convert MP3 file to raw PCM int16 using ffmpeg or subprocess."""
        wav_tmp = mp3_path + ".wav"
        try:
            # Try ffmpeg first
            import subprocess as sp
            result = sp.run(
                ["ffmpeg", "-y", "-i", mp3_path, "-f", "wav",
                 "-ar", "22050", "-ac", "1", "-acodec", "pcm_s16le", wav_tmp],
                capture_output=True, timeout=30,
            )
            if result.returncode == 0:
                pcm = self._wav_to_pcm(wav_tmp)
                if pcm:
                    return pcm
        except FileNotFoundError:
            pass  # ffmpeg not available
        except Exception as e:
            logger.debug(f"ffmpeg conversion failed: {e}")
        finally:
            Path(wav_tmp).unlink(missing_ok=True)

        # Fallback: try reading MP3 with audioop/wave through pydub or raw
        try:
            from pydub import AudioSegment
            seg = AudioSegment.from_mp3(mp3_path)
            seg = seg.set_channels(1).set_frame_rate(22050).set_sample_width(2)
            self.output_sample_rate = 22050
            return seg.raw_data
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"pydub conversion failed: {e}")

        logger.error("Cannot convert MP3 to PCM. Install ffmpeg or pydub.")
        return None

    def _wav_to_pcm(self, wav_path: str) -> Optional[bytes]:
        """Extract raw PCM int16 data from a WAV file."""
        try:
            with wave.open(wav_path, "rb") as wf:
                pcm = wf.readframes(wf.getnframes())
                self.output_sample_rate = wf.getframerate()
                # If stereo, convert to mono
                if wf.getnchannels() == 2:
                    arr = np.frombuffer(pcm, dtype=np.int16)
                    mono = ((arr[0::2].astype(np.int32) + arr[1::2].astype(np.int32)) // 2).astype(np.int16)
                    return mono.tobytes()
                return pcm
        except Exception as e:
            logger.error(f"WAV read error: {e}")
            return None

    def _aiff_to_pcm(self, aiff_path: str) -> Optional[bytes]:
        """Extract raw PCM from AIFF (macOS say output)."""
        import struct as st
        try:
            with open(aiff_path, "rb") as f:
                data = f.read()
            # Find the SSND chunk in the AIFF
            idx = data.find(b"SSND")
            if idx < 0:
                return None
            chunk_size = st.unpack(">I", data[idx+4:idx+8])[0]
            offset = st.unpack(">I", data[idx+8:idx+12])[0]
            audio_start = idx + 16 + offset
            pcm_be = data[audio_start:idx + 8 + chunk_size]
            # Convert big-endian int16 to little-endian
            arr = np.frombuffer(pcm_be, dtype=">i2").astype(np.int16)
            return arr.tobytes()
        except Exception as e:
            logger.error(f"AIFF read error: {e}")
            return None

    async def synthesize_chunked(self, text: str, chunk_size: int = 4096):
        """Synthesize and yield audio in chunks for streaming playback."""
        audio = await self.synthesize(text)
        if audio is None:
            return
        offset = 0
        while offset < len(audio):
            yield audio[offset:offset + chunk_size]
            offset += chunk_size

    @property
    def is_available(self) -> bool:
        return self._backend != "none"

    @property
    def sample_rate(self) -> int:
        return self.output_sample_rate
