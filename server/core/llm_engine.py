"""
LLM Engine — Offline using Ollama with streaming chunk-by-chunk responses.
Falls back to built-in response engine when Ollama is unavailable.
"""

import asyncio
import logging
import re
import json
import random
from datetime import datetime
from typing import AsyncGenerator, Optional, List

logger = logging.getLogger("Jarvis.LLM")

# Sentence-ending patterns for chunk splitting
SENTENCE_END = re.compile(r'[.!?;:]\s+|[.!?;:]$|\n')

# Built-in fallback responses when Ollama is not available
FALLBACK_RESPONSES = {
    "greeting": {
        "patterns": [r'\b(hello|hi|hey|good morning|good evening|good afternoon)\b'],
        "responses": [
            "Hello sir. How can I assist you today?",
            "Good day! I'm at your service.",
            "Hey there! What can I do for you?",
        ],
    },
    "how_are_you": {
        "patterns": [r'how are you|how do you do|how\'s it going'],
        "responses": [
            "I'm functioning at optimal capacity, sir. Thank you for asking.",
            "All systems operational. How may I help you?",
        ],
    },
    "thanks": {
        "patterns": [r'\b(thank|thanks|thx|appreciate)\b'],
        "responses": [
            "You're welcome, sir.",
            "Happy to help.",
            "Anytime, sir.",
        ],
    },
    "name": {
        "patterns": [r'(what.*your name|who are you|what are you)'],
        "responses": [
            "I am Jarvis, your personal AI assistant. Currently running in offline mode without Ollama, but I can still handle basic commands, set timers, take notes, and more.",
        ],
    },
    "capability": {
        "patterns": [r'(what can you do|help|capabilities|features)'],
        "responses": [
            "I can set timers, take notes, control smart home devices, tell you the time, and respond to basic queries. For full conversational AI, please install and start Ollama with a language model.",
        ],
    },
    "joke": {
        "patterns": [r'\b(joke|funny|laugh|humor)\b'],
        "responses": [
            "Why do programmers prefer dark mode? Because light attracts bugs, sir.",
            "There are only 10 types of people in the world: those who understand binary and those who don't.",
            "I tried to write a joke about recursion, but first I need to tell you a joke about recursion.",
        ],
    },
    "goodbye": {
        "patterns": [r'\b(bye|goodbye|see you|later|quit|exit)\b'],
        "responses": [
            "Goodbye, sir. I'll be here when you need me.",
            "Until next time. All systems on standby.",
        ],
    },
}


class LLMEngine:
    """Offline LLM via Ollama with streaming, fallback to built-in responses."""

    def __init__(self, config: dict):
        self.model = config.get("model", "llama3.2:3b")
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 512)
        self.system_prompt = config.get("system_prompt", "You are Jarvis, a helpful AI assistant.")
        self._conversation_history: List[dict] = []
        self._max_history = 20
        self._ollama_available: Optional[bool] = None  # None = unchecked

    async def generate_stream(
        self, user_text: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        """
        Stream LLM response chunk-by-chunk (sentence-level).
        Falls back to built-in responses if Ollama is unreachable.
        """
        # Quick check if Ollama is available (cached, re-checked periodically)
        if self._ollama_available is None:
            self._ollama_available = await self._check_ollama(timeout=3)

        if self._ollama_available:
            try:
                yielded = False
                async for chunk in self._stream_ollama(user_text, context):
                    yielded = True
                    yield chunk
                if yielded:
                    return
            except Exception as e:
                logger.warning(f"Ollama failed, using fallback: {e}")
                self._ollama_available = False

        # Fallback: built-in response engine
        async for chunk in self._fallback_response(user_text):
            yield chunk

    async def _stream_ollama(
        self, user_text: str, context: Optional[dict] = None
    ) -> AsyncGenerator[dict, None]:
        """Stream from Ollama with proper timeout handling."""
        import aiohttp

        messages = [{"role": "system", "content": self._build_system_prompt(context)}]
        messages.extend(self._conversation_history[-self._max_history:])
        messages.append({"role": "user", "content": user_text})

        self._conversation_history.append({"role": "user", "content": user_text})

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        full_response = ""
        sentence_buffer = ""

        # Short connect timeout, longer total timeout
        timeout = aiohttp.ClientTimeout(total=90, connect=5)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=timeout,
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama error {response.status}: {error_text}")
                    raise ConnectionError(f"Ollama returned {response.status}")

                async for line in response.content:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if data.get("done", False):
                        if sentence_buffer.strip():
                            yield {
                                "text": sentence_buffer,
                                "done": True,
                                "sentence": sentence_buffer.strip(),
                            }
                            full_response += sentence_buffer
                        else:
                            yield {"text": "", "done": True, "sentence": None}
                        break

                    token = data.get("message", {}).get("content", "")
                    if not token:
                        continue

                    sentence_buffer += token
                    sentences = self._split_sentences(sentence_buffer)

                    if len(sentences) > 1:
                        for sent in sentences[:-1]:
                            sent = sent.strip()
                            if sent:
                                full_response += sent + " "
                                yield {"text": sent, "done": False, "sentence": sent}
                        sentence_buffer = sentences[-1]
                    else:
                        yield {"text": token, "done": False, "sentence": None}

        self._conversation_history.append(
            {"role": "assistant", "content": full_response.strip()}
        )

    async def _fallback_response(self, user_text: str) -> AsyncGenerator[dict, None]:
        """Generate a response from built-in patterns when Ollama is unavailable."""
        text_lower = user_text.lower()
        response = None

        for category, data in FALLBACK_RESPONSES.items():
            for pattern in data["patterns"]:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    response = random.choice(data["responses"])
                    break
            if response:
                break

        if not response:
            response = (
                f"I heard you say: \"{user_text}\". "
                f"I'm currently running without a language model. "
                f"To get full AI responses, install Ollama from ollama.ai "
                f"and run: ollama pull llama3.2:3b"
            )

        logger.info(f"Fallback response: {response}")
        yield {"text": response, "done": True, "sentence": response}

    async def _check_ollama(self, timeout: int = 3) -> bool:
        """Quick check if Ollama is reachable."""
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m["name"] for m in data.get("models", [])]
                        has_model = any(self.model in m for m in models)
                        if has_model:
                            logger.info(f"Ollama available with model '{self.model}'")
                        else:
                            logger.warning(
                                f"Ollama running but model '{self.model}' not found. "
                                f"Available: {models}. Run: ollama pull {self.model}"
                            )
                        return has_model
        except Exception:
            logger.warning(
                f"Ollama not reachable at {self.base_url}. "
                f"Using built-in fallback responses. "
                f"Install Ollama from https://ollama.ai for full AI."
            )
        return False

    def _build_system_prompt(self, context: Optional[dict] = None) -> str:
        prompt = self.system_prompt
        if context:
            if "time" in context:
                prompt += f"\nCurrent time: {context['time']}"
            if "active_timers" in context:
                prompt += f"\nActive timers: {context['active_timers']}"
            if "features" in context:
                prompt += f"\nAvailable features: {', '.join(context['features'])}"
        return prompt

    def _split_sentences(self, text: str) -> list:
        """Split text at sentence boundaries while preserving the text."""
        result = []
        pos = 0
        for match in SENTENCE_END.finditer(text):
            end = match.end()
            result.append(text[pos:end])
            pos = end
        if pos < len(text):
            result.append(text[pos:])
        return result if result else [text]

    def clear_history(self):
        """Clear conversation history."""
        self._conversation_history.clear()
        logger.info("Conversation history cleared")
        logger.info("Conversation history cleared")

    async def check_available(self) -> bool:
        """Check if Ollama is running and model is available."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m["name"] for m in data.get("models", [])]
                        available = any(self.model in m for m in models)
                        if available:
                            logger.info(f"LLM model '{self.model}' is available")
                        else:
                            logger.warning(
                                f"Model '{self.model}' not found. "
                                f"Available: {models}. "
                                f"Run: ollama pull {self.model}"
                            )
                        return available
        except Exception as e:
            logger.error(f"Cannot reach Ollama at {self.base_url}: {e}")
        return False
