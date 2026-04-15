"""
Parallel Pipeline — The core of Jarvis's speed.
Processes STT → LLM → TTS in parallel, streaming chunks as soon as they're ready.

Architecture:
  Audio → [STT] → text → [Intent Detection] → [LLM stream] → chunks → [TTS parallel] → audio chunks
                                                    ↓
                                              [Feature Actions]

The key insight: LLM streams tokens into sentence buffers. As soon as a sentence
is complete, it's immediately sent to TTS while the LLM continues generating the
next sentence. This overlapping reduces total latency significantly.
"""

import asyncio
import logging
import re
import time
from datetime import datetime
from typing import AsyncGenerator, Dict, Optional

from .stt_engine import STTEngine
from .tts_engine import TTSEngine
from .llm_engine import LLMEngine

logger = logging.getLogger("Jarvis.Pipeline")

# Intent detection patterns
INTENT_PATTERNS = {
    "timer": re.compile(
        r'\b(set|start|create)\b.*\b(timer|alarm|countdown|reminder)\b',
        re.IGNORECASE,
    ),
    "cancel_timer": re.compile(
        r'\b(cancel|stop|delete|remove)\b.*\b(timer|alarm|countdown|reminder)\b',
        re.IGNORECASE,
    ),
    "music_play": re.compile(
        r'\b(play|start|resume)\b.*\b(music|song|track|audio)\b',
        re.IGNORECASE,
    ),
    "music_stop": re.compile(
        r'\b(stop|pause|halt)\b.*\b(music|song|track|audio)\b',
        re.IGNORECASE,
    ),
    "music_next": re.compile(r'\b(next|skip)\b.*\b(song|track)\b', re.IGNORECASE),
    "volume_up": re.compile(
        r'\b(increase|raise|turn up|louder)\b.*\b(volume|sound)\b', re.IGNORECASE
    ),
    "volume_down": re.compile(
        r'\b(decrease|lower|turn down|quieter|softer)\b.*\b(volume|sound)\b',
        re.IGNORECASE,
    ),
    "note_save": re.compile(
        r'\b(save|write|create|take|make)\b.*\b(note|memo|reminder)\b',
        re.IGNORECASE,
    ),
    "note_read": re.compile(
        r'\b(read|show|list|what|recall)\b.*\b(note|notes|memo|memos)\b',
        re.IGNORECASE,
    ),
    "home_lights_on": re.compile(
        r'\b(turn on|switch on|enable)\b.*\b(light|lights|lamp|lamps)\b',
        re.IGNORECASE,
    ),
    "home_lights_off": re.compile(
        r'\b(turn off|switch off|disable)\b.*\b(light|lights|lamp|lamps)\b',
        re.IGNORECASE,
    ),
    "time_query": re.compile(
        r'\b(what|tell)\b.*\b(time|date|day)\b', re.IGNORECASE
    ),
    "weather": re.compile(
        r'\b(what|how|tell)\b.*\b(weather|temperature|forecast)\b', re.IGNORECASE
    ),
    "clear_history": re.compile(
        r'\b(clear|reset|forget)\b.*\b(history|conversation|memory|chat)\b',
        re.IGNORECASE,
    ),
    "who_are_you": re.compile(
        r'\b(who|what)\b.*\b(are you|your name)\b', re.IGNORECASE
    ),
}


class ParallelPipeline:
    """
    Orchestrates the parallel STT → LLM → TTS pipeline.
    Maximizes throughput by overlapping LLM generation with TTS synthesis.
    """

    def __init__(
        self,
        stt: STTEngine,
        llm: LLMEngine,
        tts: TTSEngine,
        features: Dict,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.features = features
        self._tts_queue: asyncio.Queue = asyncio.Queue(maxsize=10)

    async def process_audio(self, audio_data: bytes) -> AsyncGenerator[dict, None]:
        """
        Full pipeline: Audio → STT → Intent → LLM(stream) → TTS(parallel) → Audio chunks.

        Yields events:
          {"type": "transcript", "text": str}
          {"type": "llm_chunk", "text": str, "done": bool}
          {"type": "audio_chunk", "audio": bytes}
          {"type": "action", "action": str, "params": dict}
          {"type": "error", "message": str}
        """
        start_time = time.monotonic()

        # Step 1: STT — Convert audio to text
        logger.info("Pipeline: Starting STT...")
        stt_start = time.monotonic()

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None, self.stt.transcribe, audio_data
        )

        stt_duration = time.monotonic() - stt_start
        logger.info(f"Pipeline: STT completed in {stt_duration:.2f}s")

        if not transcript:
            yield {"type": "error", "message": "I didn't catch that. Could you repeat?"}
            return

        # Filter out wake-word-only utterances (user just said "Jarvis")
        WAKE_ONLY = {"jarvis", "jarves", "jervis", "hijaris", "hey jarvis",
                      "hi jarvis", "jarvus", "jarvas", "service", "jarvi"}
        cleaned = transcript.lower().strip().rstrip('.!?,')
        if cleaned in WAKE_ONLY:
            logger.info(f"Pipeline: Wake word only ('{transcript}'), waiting for command")
            yield {"type": "transcript", "text": transcript}
            return

        yield {"type": "transcript", "text": transcript}

        # Step 2+3+4: Process text through intent detection + LLM + TTS
        async for event in self.process_text(transcript):
            yield event

        total_time = time.monotonic() - start_time
        logger.info(f"Pipeline: Total processing time: {total_time:.2f}s")

    async def process_text(self, text: str) -> AsyncGenerator[dict, None]:
        """
        Process text: Intent Detection → LLM(stream) → TTS(parallel).
        """
        # Step 2: Intent Detection — Check for actionable commands
        intent = self._detect_intent(text)
        if intent:
            logger.info(f"Pipeline: Detected intent: {intent}")
            action_result = await self._handle_intent(intent, text)
            if action_result:
                yield {"type": "action", "action": intent, "params": action_result.get("params", {})}

                # If the action has a response, use that instead of LLM
                if "response" in action_result:
                    response_text = action_result["response"]
                    yield {"type": "llm_chunk", "text": response_text, "done": True}

                    # Synthesize the action response
                    audio = await self.tts.synthesize(response_text)
                    if audio:
                        logger.info(f"Pipeline: TTS produced {len(audio)} bytes audio")
                        yield {"type": "audio_chunk", "audio": audio}
                    else:
                        logger.warning("Pipeline: TTS returned no audio")
                    return

        # Step 3+4: Parallel LLM streaming + TTS synthesis
        # Use a queue to stream TTS audio as soon as each sentence is ready
        tts_results: asyncio.Queue = asyncio.Queue()
        tts_done = asyncio.Event()
        tts_task = asyncio.create_task(
            self._tts_worker(tts_results, tts_done)
        )

        context = self._build_context()

        try:
            # Stream LLM response, pushing complete sentences to TTS queue
            async for chunk in self.llm.generate_stream(text, context):
                yield {"type": "llm_chunk", "text": chunk["text"], "done": chunk["done"]}

                # When a complete sentence is found, queue it for TTS
                if chunk.get("sentence"):
                    await self._tts_queue.put(chunk["sentence"])

                # Yield any TTS audio that's ready NOW (don't wait)
                while not tts_results.empty():
                    audio = tts_results.get_nowait()
                    if audio:
                        yield {"type": "audio_chunk", "audio": audio}

                if chunk["done"]:
                    # Signal TTS worker to finish
                    await self._tts_queue.put(None)

            # Wait for remaining TTS to finish
            await tts_task

            # Drain remaining audio results
            while not tts_results.empty():
                audio = await tts_results.get()
                if audio:
                    yield {"type": "audio_chunk", "audio": audio}

        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            await self._tts_queue.put(None)
            yield {"type": "error", "message": str(e)}

    async def _tts_worker(self, results_queue: asyncio.Queue, done_event: asyncio.Event = None):
        """
        Background worker that synthesizes TTS for each sentence as it arrives.
        This runs in PARALLEL with LLM generation for minimum latency.
        """
        while True:
            sentence = await self._tts_queue.get()
            if sentence is None:
                break

            try:
                audio = await self.tts.synthesize(sentence)
                if audio:
                    await results_queue.put(audio)
            except Exception as e:
                logger.error(f"TTS worker error: {e}")

    def _detect_intent(self, text: str) -> Optional[str]:
        """Fast regex-based intent detection."""
        for intent_name, pattern in INTENT_PATTERNS.items():
            if pattern.search(text):
                return intent_name
        return None

    async def _handle_intent(self, intent: str, text: str) -> Optional[dict]:
        """Handle detected intent by delegating to feature modules."""
        try:
            if intent == "time_query":
                now = datetime.now()
                return {
                    "response": f"It's currently {now.strftime('%I:%M %p')} on {now.strftime('%A, %B %d, %Y')}.",
                    "params": {"time": now.isoformat()},
                }

            if intent == "who_are_you":
                return {
                    "response": "I am Jarvis, your personal AI assistant. I'm here to help you with anything you need, sir.",
                    "params": {},
                }

            if intent == "clear_history":
                self.llm.clear_history()
                return {
                    "response": "Conversation history has been cleared, sir.",
                    "params": {},
                }

            if intent.startswith("timer") and "timers" in self.features:
                return await self.features["timers"].handle(intent, text)

            if intent.startswith("music") and "music" in self.features:
                return await self.features["music"].handle(intent, text)

            if intent.startswith("note") and "notes" in self.features:
                return await self.features["notes"].handle(intent, text)

            if intent.startswith("home") and "home" in self.features:
                return await self.features["home"].handle(intent, text)

            if intent.startswith("volume") and "system" in self.features:
                return await self.features["system"].handle(intent, text)

        except Exception as e:
            logger.error(f"Intent handling error for '{intent}': {e}")

        return None

    async def run_diagnostics(self) -> dict:
        """
        Run a full self-check of all subsystems.
        Returns a dict with status of each service and a spoken summary.
        """
        import platform as plat

        results = {}
        ok_count = 0
        total = 0

        # 1. STT check
        total += 1
        if self.stt.is_available:
            results["stt"] = {"status": "online", "detail": f"Whisper {self.stt.model_size}"}
            ok_count += 1
        else:
            results["stt"] = {"status": "offline", "detail": "faster-whisper not loaded"}

        # 2. LLM check
        total += 1
        ollama_ok = await self.llm._check_ollama(timeout=1)
        self.llm._ollama_available = ollama_ok
        if ollama_ok:
            results["llm"] = {"status": "online", "detail": f"Ollama {self.llm.model}"}
            ok_count += 1
        else:
            results["llm"] = {"status": "fallback", "detail": "Built-in responses (Ollama not found)"}
            ok_count += 1  # fallback still works

        # 3. TTS check
        total += 1
        if self.tts.is_available:
            results["tts"] = {"status": "online", "detail": f"Backend: {self.tts._backend}"}
            ok_count += 1
        else:
            results["tts"] = {"status": "offline", "detail": "No TTS backend"}

        # 4. Feature checks
        for name, feature in self.features.items():
            total += 1
            results[f"feature_{name}"] = {"status": "online", "detail": name.replace('_', ' ').title()}
            ok_count += 1

        # Build spoken summary (keep it SHORT for fast TTS)
        lines = []
        lines.append(f"Jarvis online, sir.")
        lines.append(f"{ok_count} of {total} systems operational.")

        # LLM warning only
        llm_s = results["llm"]
        if llm_s["status"] != "online":
            lines.append("Language model in fallback mode.")

        lines.append("Awaiting your command.")

        summary = " ".join(lines)
        results["_summary"] = summary
        results["_ok"] = ok_count
        results["_total"] = total

        # Detailed text summary (shown on screen, not spoken)
        detail_lines = [f"Jarvis V0.1 | {plat.system()} {plat.machine()} | {ok_count}/{total} systems OK"]
        for k, v in results.items():
            if not k.startswith("_") and not k.startswith("feature_"):
                detail_lines.append(f"  {k.upper()}: {v['status']} — {v['detail']}")
        feature_names = [v["detail"] for k, v in results.items() if k.startswith("feature_")]
        if feature_names:
            detail_lines.append(f"  Modules: {', '.join(feature_names)}")
        results["_detailed"] = " | ".join(detail_lines)

        logger.info(f"Diagnostics: {ok_count}/{total} systems OK")
        return results

    def _build_context(self) -> dict:
        """Build context info for LLM prompt enrichment."""
        ctx = {
            "time": datetime.now().strftime("%I:%M %p, %A %B %d, %Y"),
            "features": list(self.features.keys()),
        }

        if "timers" in self.features:
            active = self.features["timers"].get_active_timers()
            if active:
                ctx["active_timers"] = active

        return ctx
