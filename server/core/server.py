"""
WebSocket Server — Handles ESP32 client connections and message routing.
Supports multiple simultaneous clients with independent sessions.
"""

import asyncio
import json
import logging
import struct
from typing import Dict, Optional

import websockets
from websockets.server import WebSocketServerProtocol

from .pipeline import ParallelPipeline

logger = logging.getLogger("Jarvis.Server")


class ClientSession:
    """Represents a connected ESP32 client."""

    def __init__(self, ws: WebSocketServerProtocol, client_id: str):
        self.ws = ws
        self.client_id = client_id
        self.is_recording = False
        self.audio_buffer = bytearray()
        self.state = "idle"  # idle, listening, processing, speaking

    async def send_json(self, data: dict):
        try:
            await self.ws.send(json.dumps(data))
        except websockets.ConnectionClosed:
            logger.warning(f"Client {self.client_id} disconnected during send")

    async def send_audio(self, audio_data: bytes, sample_rate: int = 22050):
        try:
            # Protocol: 0x01 + 4-byte sample_rate (little-endian) + audio data
            # Chunk large audio to avoid WebSocket message size limits
            CHUNK = 512 * 1024  # 512KB per message
            offset = 0
            while offset < len(audio_data):
                chunk = audio_data[offset:offset + CHUNK]
                header = struct.pack('<BI', 0x01, sample_rate)
                await self.ws.send(header + chunk)
                offset += CHUNK
        except websockets.ConnectionClosed:
            logger.warning(f"Client {self.client_id} disconnected during audio send")

    async def send_state(self, state: str, **kwargs):
        self.state = state
        msg = {"type": "state", "state": state}
        msg.update(kwargs)
        await self.send_json(msg)


class JarvisServer:
    """WebSocket server that bridges ESP32 devices to the Jarvis pipeline."""

    def __init__(self, config: dict, pipeline: ParallelPipeline):
        self.host = config["host"]
        self.port = config["port"]
        self.max_clients = config.get("max_clients", 5)
        self.pipeline = pipeline
        self.clients: Dict[str, ClientSession] = {}
        self._server = None
        self._running = False
        self._boot_check_done = False
        self._diagnostics: Optional[dict] = None

    async def start(self):
        self._running = True
        self._server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            max_size=10 * 2**20,  # 10MB max message
            ping_interval=20,
            ping_timeout=10,
        )
        logger.info(f"WebSocket server listening on ws://{self.host}:{self.port}")
        await self._server.wait_closed()

    async def shutdown(self):
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        # Close all client connections
        for session in list(self.clients.values()):
            await session.ws.close()
        self.clients.clear()
        logger.info("Server shut down cleanly")

    async def _handle_client(self, ws: WebSocketServerProtocol):
        client_id = f"{ws.remote_address[0]}:{ws.remote_address[1]}"

        if len(self.clients) >= self.max_clients:
            await ws.close(1013, "Max clients reached")
            logger.warning(f"Rejected client {client_id}: max clients reached")
            return

        session = ClientSession(ws, client_id)
        self.clients[client_id] = session
        logger.info(f"Client connected: {client_id}")

        try:
            # Send welcome
            await session.send_json({
                "type": "welcome",
                "message": "Jarvis online. Awaiting your command.",
                "version": "0.1",
            })

            # First client triggers boot self-check; later clients get cached results
            if not self._boot_check_done:
                self._boot_check_done = True
                await self._run_boot_check(session)
            elif self._diagnostics:
                await self._send_cached_diagnostics(session)

            await session.send_state("idle")

            async for message in ws:
                if not self._running:
                    break
                await self._process_message(session, message)

        except websockets.ConnectionClosed as e:
            logger.info(f"Client {client_id} disconnected: {e.code}")
        except Exception as e:
            logger.error(f"Error with client {client_id}: {e}", exc_info=True)
        finally:
            self.clients.pop(client_id, None)
            logger.info(f"Client removed: {client_id}")

    async def _process_message(self, session: ClientSession, message):
        if isinstance(message, bytes):
            await self._handle_audio(session, message)
        else:
            await self._handle_command(session, message)

    async def _handle_audio(self, session: ClientSession, data: bytes):
        if len(data) < 1:
            return

        msg_type = data[0]

        if msg_type == 0x01:
            # Audio chunk — append to buffer
            session.audio_buffer.extend(data[1:])

        elif msg_type == 0x02:
            # Recording started
            session.is_recording = True
            session.audio_buffer = bytearray()
            await session.send_state("listening")
            logger.info(f"Client {session.client_id}: Recording started")

        elif msg_type == 0x03:
            # Recording ended — process the audio
            session.is_recording = False
            audio_data = bytes(session.audio_buffer)
            session.audio_buffer = bytearray()
            logger.info(
                f"Client {session.client_id}: Recording ended, "
                f"{len(audio_data)} bytes received"
            )

            if len(audio_data) > 0:
                # Process through parallel pipeline
                await self._process_utterance(session, audio_data)
            else:
                await session.send_state("idle")

    async def _handle_command(self, session: ClientSession, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {session.client_id}")
            return

        cmd = data.get("type", "")

        if cmd == "ping":
            await session.send_json({"type": "pong"})

        elif cmd == "wake_word":
            # ESP32 detected wake word locally
            logger.info(f"Wake word detected by {session.client_id}")
            await session.send_state("listening", message="Yes, sir?")

        elif cmd == "text_input":
            # Direct text input (for testing)
            text = data.get("text", "").strip()
            if text:
                await self._process_text(session, text)

        elif cmd == "cancel":
            await session.send_state("idle")
            logger.info(f"Client {session.client_id}: Cancelled")

        elif cmd == "wake_check":
            # Client sends short audio for wake word check
            audio_b64 = data.get("audio", "")
            if audio_b64:
                import base64
                audio_bytes = base64.b64decode(audio_b64)
                await self._check_wake_word(session, audio_bytes)

        elif cmd == "set_config":
            # Runtime config update
            await session.send_json({"type": "config_ack", "status": "ok"})

    async def _process_utterance(self, session: ClientSession, audio_data: bytes):
        """Process recorded audio through the full pipeline with parallel chunking."""
        await session.send_state("processing", message="Processing...")

        try:
            # The pipeline handles: STT → LLM (chunk) → TTS (chunk) → stream back
            async for event in self.pipeline.process_audio(audio_data):
                event_type = event["type"]

                if event_type == "transcript":
                    await session.send_json({
                        "type": "transcript",
                        "text": event["text"],
                    })

                elif event_type == "llm_chunk":
                    await session.send_json({
                        "type": "response_text",
                        "text": event["text"],
                        "done": event.get("done", False),
                    })

                elif event_type == "audio_chunk":
                    await session.send_state("speaking")
                    sr = self.pipeline.tts.output_sample_rate
                    await session.send_audio(event["audio"], sample_rate=sr)

                elif event_type == "action":
                    await session.send_json({
                        "type": "action",
                        "action": event["action"],
                        "params": event.get("params", {}),
                    })

                elif event_type == "error":
                    await session.send_json({
                        "type": "error",
                        "message": event["message"],
                    })

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            await session.send_json({
                "type": "error",
                "message": "I encountered an error processing your request.",
            })

        await session.send_state("idle")

    async def _run_boot_check(self, session: ClientSession):
        """Run diagnostics on first client connect and report status."""
        logger.info("Running boot self-check...")
        await session.send_state("processing", message="Running self-check...")

        try:
            diag = await self.pipeline.run_diagnostics()
            self._diagnostics = diag
            summary = diag.get("_summary", "Self-check complete.")
            ok = diag.get("_ok", 0)
            total = diag.get("_total", 0)

            # Send detailed status to client
            status_items = []
            for key, val in diag.items():
                if key.startswith("_"):
                    continue
                status_items.append({
                    "service": key,
                    "status": val["status"],
                    "detail": val["detail"],
                })

            await session.send_json({
                "type": "diagnostics",
                "ok": ok,
                "total": total,
                "services": status_items,
                "summary": summary,
            })

            # Send the detailed summary as text (no TTS on boot for speed)
            detailed = diag.get("_detailed", summary)
            await session.send_json({
                "type": "response_text",
                "text": summary,
                "done": True,
            })

            logger.info(f"Boot check complete: {ok}/{total} systems OK")

        except Exception as e:
            logger.error(f"Boot check error: {e}", exc_info=True)
            await session.send_json({
                "type": "response_text",
                "text": "Boot self-check encountered an error, but I'm operational.",
                "done": True,
            })

    async def _send_cached_diagnostics(self, session: ClientSession):
        """Send previously computed diagnostics to a reconnecting client."""
        diag = self._diagnostics
        status_items = []
        for key, val in diag.items():
            if key.startswith("_"):
                continue
            status_items.append({
                "service": key,
                "status": val["status"],
                "detail": val["detail"],
            })

        await session.send_json({
            "type": "diagnostics",
            "ok": diag.get("_ok", 0),
            "total": diag.get("_total", 0),
            "services": status_items,
            "summary": diag.get("_summary", ""),
        })

    async def _process_text(self, session: ClientSession, text: str):
        """Process direct text input through LLM → TTS pipeline."""
        await session.send_state("processing")

        try:
            async for event in self.pipeline.process_text(text):
                event_type = event["type"]

                if event_type == "llm_chunk":
                    await session.send_json({
                        "type": "response_text",
                        "text": event["text"],
                        "done": event.get("done", False),
                    })

                elif event_type == "audio_chunk":
                    await session.send_state("speaking")
                    sr = self.pipeline.tts.output_sample_rate
                    await session.send_audio(event["audio"], sample_rate=sr)

                elif event_type == "action":
                    await session.send_json({
                        "type": "action",
                        "action": event["action"],
                        "params": event.get("params", {}),
                    })

        except Exception as e:
            logger.error(f"Text pipeline error: {e}", exc_info=True)
            await session.send_json({
                "type": "error",
                "message": "Processing error.",
            })

        await session.send_state("idle")

    async def _check_wake_word(self, session: ClientSession, audio_bytes: bytes):
        """Quick wake word check on short audio clip from browser mic."""
        if not self.pipeline.stt.is_available:
            return

        import numpy as np

        # Server-side energy gate: reject silent audio BEFORE running Whisper
        try:
            samples = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            if len(samples) == 0:
                return
            rms = np.sqrt(np.mean(samples ** 2)) / 32768.0
            if rms < 0.008:
                return  # Silent — skip Whisper entirely
        except Exception:
            return

        WAKE_PHRASES = {
            "jarvis", "jarves", "jervis", "jarvus", "jarvas",
            "hey jarvis", "hi jarvis", "hijaris", "service",
            "jarvie", "jarvi", "jarv", "javis", "jarwis",
        }

        try:
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None, self.pipeline.stt.transcribe, audio_bytes
            )

            if text:
                text_lower = text.lower().strip().rstrip('.')
                if any(w in text_lower for w in WAKE_PHRASES):
                    logger.info(f"Wake word detected: '{text}'")
                    await session.send_json({
                        "type": "wake_detected",
                        "text": text,
                    })
                    await session.send_state("listening", message="Yes, sir?")
        except Exception as e:
            logger.debug(f"Wake check error: {e}")
