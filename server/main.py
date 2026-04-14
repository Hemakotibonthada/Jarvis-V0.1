"""
JARVIS V0.1 — Main Entry Point
Starts the WebSocket server and initializes all subsystems.
"""

import asyncio
import signal
import sys
import logging
import yaml
from pathlib import Path

from core.server import JarvisServer
from core.pipeline import ParallelPipeline
from core.stt_engine import STTEngine
from core.tts_engine import TTSEngine
from core.llm_engine import LLMEngine
from features.timer_manager import TimerManager
from features.home_automation import HomeAutomation
from features.music_player import MusicPlayer
from features.notes_manager import NotesManager
from features.system_control import SystemControl
from features.knowledge_base import KnowledgeBase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("Jarvis")


def load_config() -> dict:
    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


async def main():
    logger.info("=" * 50)
    logger.info("  JARVIS V0.1 — Initializing...")
    logger.info("=" * 50)

    config = load_config()

    # Initialize engines
    logger.info("Loading STT engine (Whisper)...")
    stt = STTEngine(config["stt"])

    logger.info("Loading LLM engine (Ollama)...")
    llm = LLMEngine(config["llm"])

    logger.info("Loading TTS engine (Piper)...")
    tts = TTSEngine(config["tts"])

    # Initialize features
    features = {}

    if config["features"]["timers"]["enabled"]:
        logger.info("Initializing Timer Manager...")
        features["timers"] = TimerManager(config["features"]["timers"])

    if config["features"]["home_automation"]["enabled"]:
        logger.info("Initializing Home Automation...")
        features["home"] = HomeAutomation(config["features"]["home_automation"])

    if config["features"]["music"]["enabled"]:
        logger.info("Initializing Music Player...")
        features["music"] = MusicPlayer(config["features"]["music"])

    if config["features"]["notes"]["enabled"]:
        logger.info("Initializing Notes Manager...")
        features["notes"] = NotesManager(config["features"]["notes"])

    logger.info("Initializing System Control...")
    features["system"] = SystemControl()

    logger.info("Initializing Knowledge Base...")
    features["knowledge"] = KnowledgeBase()

    # Build parallel pipeline
    logger.info("Building parallel processing pipeline...")
    pipeline = ParallelPipeline(stt, llm, tts, features)

    # Start WebSocket server
    server = JarvisServer(config["server"], pipeline)

    # Handle shutdown
    loop = asyncio.get_running_loop()

    def shutdown_handler():
        logger.info("Shutting down Jarvis...")
        asyncio.ensure_future(server.shutdown())

    if sys.platform != "win32":
        loop.add_signal_handler(signal.SIGINT, shutdown_handler)
        loop.add_signal_handler(signal.SIGTERM, shutdown_handler)

    # Start HTTP server for web UI
    web_port = config["server"].get("web_port", 8080)
    from core.web_server import start_web_server
    web_runner = await start_web_server(web_port)

    logger.info("=" * 50)
    logger.info("  JARVIS V0.1 — Online and Ready")
    logger.info(f"  WebSocket : ws://{config['server']['host']}:{config['server']['port']}")
    logger.info(f"  Control UI: http://localhost:{web_port}")
    logger.info("=" * 50)

    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Jarvis shut down by user.")
