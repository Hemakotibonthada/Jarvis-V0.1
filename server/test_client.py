"""
PC Test Client — Test Jarvis server without ESP32 hardware.
Uses PC microphone and speakers. Supports:
  - Say "Jarvis" to activate (wake word via Whisper)
  - Double-clap to activate
  - Press Enter for manual recording
  - Type text directly with 't <message>'
"""

import asyncio
import json
import struct
import sys
import threading
import time
import numpy as np

try:
    import sounddevice as sd
except ImportError:
    print("Install sounddevice: pip install sounddevice")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


# ── Config ──────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 4096
SERVER_URL = "ws://localhost:8765"
PLAYBACK_RATE = 22050

# Silence detection
SILENCE_RMS = 0.015          # RMS threshold for silence (float32)
SILENCE_SECONDS = 1.5        # How long silence = end of speech
MAX_RECORD_SECONDS = 15      # Hard cap

# Clap detection
CLAP_ENERGY = 0.12           # RMS threshold
CLAP_CREST = 3.5             # peak/RMS ratio
CLAP_GAP_MIN = 0.12          # seconds between claps (min)
CLAP_GAP_MAX = 0.75          # seconds between claps (max)

# Wake word
WAKE_PHRASES = {"jarvis", "jarves", "jervis", "hey jarvis"}
WAKE_CHECK_INTERVAL = 2.0    # seconds between wake word checks


# ── Clap Detector ───────────────────────────────────
class ClapDetector:
    def __init__(self):
        self._first_time = 0.0
        self._waiting = False
        self._cooldown = 0.0

    def check(self, audio_f32: np.ndarray) -> bool:
        now = time.time()
        if now < self._cooldown:
            return False

        rms = float(np.sqrt(np.mean(audio_f32 ** 2)))
        if rms < 1e-6:
            return False
        peak = float(np.max(np.abs(audio_f32)))
        crest = peak / rms

        is_clap = rms > CLAP_ENERGY and crest > CLAP_CREST

        if is_clap:
            if self._waiting:
                gap = now - self._first_time
                if CLAP_GAP_MIN <= gap <= CLAP_GAP_MAX:
                    self._waiting = False
                    self._cooldown = now + 1.5
                    return True
                if gap > CLAP_GAP_MAX:
                    self._first_time = now
            else:
                self._first_time = now
                self._waiting = True

        if self._waiting and (now - self._first_time) > CLAP_GAP_MAX:
            self._waiting = False

        return False


# ── Main Client ─────────────────────────────────────
class JarvisClient:
    def __init__(self):
        self.ws = None
        self.state = "idle"
        self.clap = ClapDetector()
        self._monitor_stream = None
        self._monitoring = False
        self._triggered = asyncio.Event()
        self._playback_queue = asyncio.Queue()
        self._loop = None

        # Wake word STT model (lazy loaded)
        self._wake_model = None
        self._wake_available = False
        self._wake_buf: list = []
        self._wake_buf_dur = 0.0
        self._wake_lock = threading.Lock()

        try:
            from faster_whisper import WhisperModel
            self._wake_available = True
        except ImportError:
            pass

    # ── Connection ──────────────────────────────────
    async def run(self):
        self._loop = asyncio.get_running_loop()

        print(f"\n  Connecting to {SERVER_URL} ...")
        try:
            self.ws = await websockets.connect(SERVER_URL, max_size=10 * 2**20)
        except Exception as e:
            print(f"  Cannot connect to server: {e}")
            print("  Make sure the Jarvis server is running: python main.py")
            return

        print("  Connected!\n")

        tasks = [
            asyncio.create_task(self._receiver()),
            asyncio.create_task(self._player()),
            asyncio.create_task(self._main_loop()),
        ]

        try:
            await asyncio.gather(*tasks)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            self._stop_monitor()
            for t in tasks:
                t.cancel()
            await self.ws.close()
            print("\n  Disconnected.")

    # ── Receive messages from server ────────────────
    async def _receiver(self):
        try:
            async for msg in self.ws:
                if isinstance(msg, bytes) and len(msg) > 5 and msg[0] == 0x01:
                    # Binary: 0x01 + 4-byte sample_rate (LE) + PCM data
                    sr = struct.unpack('<I', msg[1:5])[0]
                    await self._playback_queue.put((sr, msg[5:]))
                elif isinstance(msg, str):
                    data = json.loads(msg)
                    t = data.get("type", "")
                    if t == "state":
                        self.state = data.get("state", "idle")
                        s = self.state.upper()
                        extra = data.get("message", "")
                        label = f"  [{s}]" + (f" {extra}" if extra else "")
                        print(label)
                        if self.state == "idle":
                            self._schedule_restart_monitor()
                    elif t == "diagnostics":
                        self._print_diagnostics(data)
                    elif t == "transcript":
                        print(f'  You: "{data.get("text", "")}"')
                    elif t == "response_text":
                        txt = data.get("text", "")
                        if data.get("done"):
                            print(f"\n  Jarvis: {txt}")
                        else:
                            print(txt, end="", flush=True)
                    elif t == "welcome":
                        print(f"  {data.get('message', '')}")
                    elif t == "action":
                        print(f'  [Action: {data.get("action","")}]')
                    elif t == "error":
                        print(f'  [Error: {data.get("message","")}]')
        except websockets.ConnectionClosed:
            print("\n  Server disconnected.")

    def _print_diagnostics(self, data: dict):
        """Pretty-print the boot diagnostics report."""
        ok = data.get("ok", 0)
        total = data.get("total", 0)
        services = data.get("services", [])

        print("\n  " + "=" * 48)
        print("    JARVIS  BOOT  SELF-CHECK")
        print("  " + "=" * 48)

        status_icons = {"online": "+", "fallback": "~", "offline": "X"}

        for svc in services:
            icon = status_icons.get(svc["status"], "?")
            name = svc["service"].replace("feature_", "").replace("_", " ").upper()
            status = svc["status"].upper()
            detail = svc.get("detail", "")
            pad = max(1, 18 - len(name))
            print(f"    [{icon}] {name}{' ' * pad}{status:>8}  {detail}")

        print("  " + "-" * 48)
        print(f"    Result: {ok}/{total} systems operational")
        print("  " + "=" * 48 + "\n")

    # ── Play audio from server ──────────────────────
    async def _player(self):
        while True:
            sr, pcm = await self._playback_queue.get()
            try:
                arr = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
                if len(arr) < 100:
                    continue  # skip tiny/empty chunks
                # Play in executor to not block the event loop
                await self._loop.run_in_executor(None, self._play_sync, arr, sr)
            except Exception as e:
                print(f"  (playback error: {e})")

    def _play_sync(self, arr, sr):
        """Blocking audio playback (runs in thread)."""
        try:
            sd.play(arr, samplerate=sr)
            sd.wait()
        except Exception as e:
            print(f"  (audio error: {e})")

    # ── Main interaction loop ───────────────────────
    async def _main_loop(self):
        await asyncio.sleep(1)  # wait for welcome

        print("=" * 52)
        print("  JARVIS — Voice Assistant Test Client")
        print("  ─────────────────────────────────────")
        print("   Enter     = Record (auto-stops on silence)")
        print("   t <text>  = Send text command")
        print("   l         = Toggle always-on listening")
        print("   q         = Quit")
        print("=" * 52)

        self._start_monitor()

        while True:
            # Wait for either user input OR a wake/clap trigger
            input_task = asyncio.ensure_future(
                self._loop.run_in_executor(None, self._blocking_input)
            )
            trigger_task = asyncio.ensure_future(self._triggered.wait())

            done, pending = await asyncio.wait(
                {input_task, trigger_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for p in pending:
                p.cancel()
                try:
                    await p
                except (asyncio.CancelledError, Exception):
                    pass

            if trigger_task in done:
                # Wake word or clap triggered
                self._triggered.clear()
                await self._auto_record()
                continue

            # User typed something
            try:
                cmd = input_task.result().strip()
            except (asyncio.CancelledError, Exception):
                continue

            if cmd == "q":
                return

            elif cmd.startswith("t "):
                text = cmd[2:].strip()
                if text:
                    await self.ws.send(json.dumps({"type": "text_input", "text": text}))
                    print(f'  Sent: "{text}"')

            elif cmd == "l":
                if self._monitoring:
                    self._stop_monitor()
                    print("  Listening: OFF")
                else:
                    self._start_monitor()
                    print("  Listening: ON")

            elif cmd == "":
                await self._auto_record()

    def _blocking_input(self) -> str:
        try:
            return input("\n> ")
        except EOFError:
            return "q"

    # ── Auto-record with silence detection ──────────
    async def _auto_record(self):
        self._stop_monitor()
        self.state = "listening"

        print("  Speak now... (auto-stops on silence)")

        # Tell server we're recording
        await self.ws.send(bytes([0x02]))

        chunks: list = []
        silence_start = [0.0]
        speech_seen = [False]
        recording = [True]
        t0 = time.time()

        def cb(indata, frames, ti, status):
            if not recording[0]:
                return
            chunks.append(indata.copy())

            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            if rms > SILENCE_RMS:
                speech_seen[0] = True
                silence_start[0] = time.time()
            elif speech_seen[0]:
                if silence_start[0] == 0:
                    silence_start[0] = time.time()
                elif (time.time() - silence_start[0]) > SILENCE_SECONDS:
                    recording[0] = False

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS,
            dtype="int16", blocksize=CHUNK_SIZE, callback=cb,
        )
        stream.start()

        while recording[0] and (time.time() - t0) < MAX_RECORD_SECONDS:
            await asyncio.sleep(0.1)

        recording[0] = False
        stream.stop()
        stream.close()

        if chunks:
            audio = np.concatenate(chunks).tobytes()
            # Send in chunks
            for i in range(0, len(audio), CHUNK_SIZE):
                await self.ws.send(bytes([0x01]) + audio[i:i + CHUNK_SIZE])
            await self.ws.send(bytes([0x03]))
            dur = len(audio) / (SAMPLE_RATE * 2)  # 2 bytes per int16 sample
            print(f"  Sent {dur:.1f}s of audio ({len(audio)} bytes)")
        else:
            await self.ws.send(bytes([0x03]))
            print("  (no audio captured)")

    # ── Background monitor (wake word + clap) ───────
    def _start_monitor(self):
        if self._monitoring:
            return
        self._monitoring = True
        self._wake_buf = []
        self._wake_buf_dur = 0.0

        def cb(indata, frames, ti, status):
            if not self._monitoring or self.state != "idle":
                return

            f32 = indata[:, 0].astype(np.float32)

            # Clap check
            if self.clap.check(f32):
                print("\n  ** DOUBLE-CLAP! **")
                self._loop.call_soon_threadsafe(self._triggered.set)
                return

            # Accumulate for wake word
            if self._wake_available:
                with self._wake_lock:
                    self._wake_buf.append(f32.copy())
                    self._wake_buf_dur += frames / SAMPLE_RATE

                    if self._wake_buf_dur >= WAKE_CHECK_INTERVAL:
                        audio = np.concatenate(self._wake_buf)
                        self._wake_buf = [audio[-int(SAMPLE_RATE * 0.3):]]
                        self._wake_buf_dur = 0.3
                        threading.Thread(
                            target=self._check_wake, args=(audio,), daemon=True
                        ).start()

        try:
            self._monitor_stream = sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS,
                dtype="float32", blocksize=1024, callback=cb,
            )
            self._monitor_stream.start()
            modes = ["double-clap"]
            if self._wake_available:
                modes.insert(0, "say 'Jarvis'")
            print(f"  Listening for: {' / '.join(modes)}")
        except Exception as e:
            print(f"  Mic error: {e}")
            self._monitoring = False

    def _stop_monitor(self):
        self._monitoring = False
        if self._monitor_stream:
            try:
                self._monitor_stream.stop()
                self._monitor_stream.close()
            except Exception:
                pass
            self._monitor_stream = None

    def _schedule_restart_monitor(self):
        """Restart monitoring after server returns to idle."""
        if self._loop and not self._monitoring:
            self._loop.call_later(0.5, self._start_monitor)

    def _check_wake(self, audio_f32: np.ndarray):
        """Run whisper on background audio looking for 'Jarvis'."""
        try:
            if self._wake_model is None:
                from faster_whisper import WhisperModel
                self._wake_model = WhisperModel(
                    "tiny.en", device="cpu", compute_type="int8"
                )

            segments, _ = self._wake_model.transcribe(
                audio_f32, beam_size=1, language="en",
                vad_filter=True,
                vad_parameters={"threshold": 0.5},
            )
            text = " ".join(s.text.strip().lower() for s in segments)
            if text and any(w in text for w in WAKE_PHRASES):
                print(f'\n  ** Wake word: "{text.strip()}" **')
                self._loop.call_soon_threadsafe(self._triggered.set)
        except Exception:
            pass


# ── Entry point ─────────────────────────────────────
async def main():
    client = JarvisClient()
    await client.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n  Bye!")
