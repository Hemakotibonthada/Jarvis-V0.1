"""
Model Setup Script — Downloads required offline models for Jarvis.
"""

import os
import sys
import logging
import subprocess
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("Setup")

MODELS_DIR = Path(__file__).parent / "models"
TTS_DIR = MODELS_DIR / "tts"

# Piper TTS model URLs (from official repo)
PIPER_MODELS = {
    "en_US-lessac-medium": {
        "onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "json": "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
    },
}


def download_file(url: str, dest: Path):
    if dest.exists():
        logger.info(f"  Already exists: {dest.name}")
        return

    logger.info(f"  Downloading: {dest.name}...")
    try:
        urllib.request.urlretrieve(url, str(dest))
        logger.info(f"  Done: {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    except Exception as e:
        logger.error(f"  Failed to download {url}: {e}")
        sys.exit(1)


def setup_piper_tts():
    logger.info("Setting up Piper TTS models...")
    TTS_DIR.mkdir(parents=True, exist_ok=True)

    for model_name, urls in PIPER_MODELS.items():
        logger.info(f"Model: {model_name}")
        download_file(urls["onnx"], TTS_DIR / f"{model_name}.onnx")
        download_file(urls["json"], TTS_DIR / f"{model_name}.onnx.json")


def setup_whisper():
    logger.info("Setting up Whisper STT model...")
    logger.info("  faster-whisper will download the model on first run.")
    logger.info("  Default model: base.en (~150MB)")
    try:
        import faster_whisper
        logger.info("  faster-whisper is installed.")
    except ImportError:
        logger.info("  Installing faster-whisper...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "faster-whisper"])


def check_ollama():
    logger.info("Checking Ollama LLM...")
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            logger.info("  Ollama is installed.")
            logger.info(f"  Available models:\n{result.stdout}")
        else:
            logger.warning("  Ollama not responding. Make sure it's running.")
    except FileNotFoundError:
        logger.warning(
            "  Ollama not found. Install from: https://ollama.ai/download\n"
            "  Then run: ollama pull llama3.2:3b"
        )
    except Exception as e:
        logger.warning(f"  Ollama check failed: {e}")


def main():
    logger.info("=" * 50)
    logger.info("  JARVIS V0.1 — Model Setup")
    logger.info("=" * 50)

    setup_piper_tts()
    setup_whisper()
    check_ollama()

    # Create data directories
    data_dirs = [
        Path("data/notes"),
        Path("data/knowledge"),
        Path("data/weather_cache"),
        Path("music"),
    ]
    for d in data_dirs:
        d.mkdir(parents=True, exist_ok=True)

    logger.info("")
    logger.info("=" * 50)
    logger.info("  Setup complete!")
    logger.info("  Next steps:")
    logger.info("  1. Install Ollama: https://ollama.ai/download")
    logger.info("  2. Pull a model: ollama pull llama3.2:3b")
    logger.info("  3. Start Jarvis: python main.py")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
