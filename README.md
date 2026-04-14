# JARVIS V0.1 — Offline AI Voice Assistant

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    ESP32 Device                              │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────────┐    │
│  │ INMP441  │  │ MAX98357 │  │  TFT Display (ST7789)  │    │
│  │   Mic    │  │ Speaker  │  │  240x240 Animations    │    │
│  └────┬─────┘  └────┬─────┘  └────────────┬───────────┘    │
│       │              │                     │                 │
│  ┌────┴──────────────┴─────────────────────┴───────────┐    │
│  │              ESP32-S3 / ESP32 WROOM                  │    │
│  │  • Wake word detection (local)                       │    │
│  │  • Audio capture & playback (I2S)                    │    │
│  │  • WebSocket client                                  │    │
│  │  • Display animation engine (eye/orb/waveform)       │    │
│  └──────────────────────┬──────────────────────────────┘    │
└─────────────────────────┼───────────────────────────────────┘
                          │ WiFi / WebSocket
┌─────────────────────────┼───────────────────────────────────┐
│              Python Server (PC/RPi)                          │
│  ┌──────────────────────┴──────────────────────────────┐    │
│  │              WebSocket Server                        │    │
│  └──────────┬───────────────────────────┬──────────────┘    │
│             │                           │                    │
│  ┌──────────┴──────────┐  ┌─────────────┴─────────────┐    │
│  │   Parallel Pipeline │  │   Feature Modules          │    │
│  │  ┌───────────────┐  │  │  • Home Automation         │    │
│  │  │ STT (Whisper) │  │  │  • Weather (offline cache) │    │
│  │  └───────┬───────┘  │  │  • Timers/Alarms           │    │
│  │  ┌───────┴───────┐  │  │  • System Control          │    │
│  │  │ LLM (Ollama)  │──│──│  • Knowledge Base          │    │
│  │  │ Chunk Stream  │  │  │  • Music Control           │    │
│  │  └───────┬───────┘  │  │  • Notes/Reminders         │    │
│  │  ┌───────┴───────┐  │  └───────────────────────────┘    │
│  │  │ TTS (Piper)   │  │                                    │
│  │  │ Chunk Stream  │  │                                    │
│  │  └───────────────┘  │                                    │
│  └─────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
```

## Features

- **Offline Voice Recognition** — Whisper (faster-whisper) running locally
- **Offline LLM** — Ollama with streaming chunk-by-chunk processing
- **Offline TTS** — Piper TTS for natural human voice
- **Parallel Pipeline** — STT → LLM (chunked) → TTS (chunked) runs in parallel
- **ESP32 Animations** — Iron Man–style eye/orb animations on TFT display
- **Wake Word Detection** — Local "Jarvis" wake word on ESP32
- **WebSocket Streaming** — Real-time bidirectional audio streaming
- **Home Automation** — Control smart devices
- **Timers & Alarms** — Set timers, reminders
- **System Control** — Volume, brightness, etc.
- **Knowledge Base** — Offline Q&A from local documents
- **Music Control** — Play/pause/skip local music

## Quick Start

### Server (Python)
```bash
cd server
pip install -r requirements.txt
# Download Piper TTS model
python setup_models.py
# Start Jarvis server
python main.py
```

### ESP32 (PlatformIO)
```bash
cd esp32-device
# Open in PlatformIO IDE or:
pio run -t upload
pio device monitor
```

## Hardware Requirements (ESP32)
- ESP32-S3 DevKit (recommended) or ESP32 WROOM
- INMP441 I2S MEMS Microphone
- MAX98357A I2S Amplifier + Speaker
- ST7789 1.3" TFT Display (240x240)
- Optional: WS2812B LED ring
