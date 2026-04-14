/*
 * JARVIS V0.1 — ESP32 Main Firmware
 * 
 * Architecture:
 *   Core 0: Audio I/O (mic capture, speaker playback) — real-time priority
 *   Core 1: Display animations, WebSocket, main logic
 *
 * Flow:
 *   Wake Word → Record → Send to Server → Receive response → Play audio
 */

#include <Arduino.h>
#include <WiFi.h>
#include "config.h"
#include "audio_manager.h"
#include "display_manager.h"
#include "ws_client.h"
#include "wake_word.h"

// ============================================================
// Global State
// ============================================================

enum JarvisState {
    STATE_BOOT,
    STATE_CONNECTING,
    STATE_IDLE,
    STATE_LISTENING,
    STATE_PROCESSING,
    STATE_SPEAKING,
    STATE_ERROR
};

volatile JarvisState currentState = STATE_BOOT;
volatile bool wakeWordDetected = false;
volatile WakeTrigger lastTriggerType = TRIGGER_NONE;

AudioManager audioManager;
DisplayManager displayManager;
WSClient wsClient;
WakeWordDetector wakeWord;

// Task handles
TaskHandle_t audioTaskHandle = NULL;
TaskHandle_t displayTaskHandle = NULL;

// ============================================================
// Audio Task — Runs on Core 0
// ============================================================

void audioTask(void* parameter) {
    Serial.println("[Audio] Task started on Core 0");

    while (true) {
        switch (currentState) {
            case STATE_IDLE:
                // Continuously sample mic for wake word AND clap detection
                if (WAKE_WORD_ENABLED || CLAP_ENABLED) {
                    int16_t samples[AUDIO_BUFFER_SIZE];
                    size_t bytesRead = audioManager.readMic(samples, AUDIO_BUFFER_SIZE);
                    
                    if (bytesRead > 0) {
                        WakeTrigger trigger = wakeWord.detect(samples, bytesRead / 2);
                        if (trigger != TRIGGER_NONE) {
                            wakeWordDetected = true;
                            lastTriggerType = trigger;
                            Serial.printf("[Audio] Activated by: %s\n",
                                trigger == TRIGGER_CLAP ? "DOUBLE CLAP" : "VOICE");
                        }
                    }
                }
                vTaskDelay(pdMS_TO_TICKS(10));
                break;

            case STATE_LISTENING:
                // Record and send audio chunks to server
                {
                    int16_t samples[AUDIO_BUFFER_SIZE];
                    size_t bytesRead = audioManager.readMic(samples, AUDIO_BUFFER_SIZE);
                    
                    if (bytesRead > 0) {
                        wsClient.sendAudioChunk((uint8_t*)samples, bytesRead);
                        
                        // Check for silence (VAD)
                        if (audioManager.isSilence(samples, bytesRead / 2)) {
                            if (audioManager.getSilenceDuration() > VAD_SILENCE_MS) {
                                // End of speech
                                wsClient.sendRecordingEnd();
                                currentState = STATE_PROCESSING;
                                Serial.println("[Audio] Silence detected, processing...");
                            }
                        } else {
                            audioManager.resetSilenceTimer();
                        }
                        
                        // Max recording limit
                        if (audioManager.getRecordingDuration() > VAD_MAX_RECORD_MS) {
                            wsClient.sendRecordingEnd();
                            currentState = STATE_PROCESSING;
                        }
                    }
                }
                vTaskDelay(pdMS_TO_TICKS(5));
                break;

            case STATE_SPEAKING:
                // Play received audio
                if (audioManager.hasAudioToPlay()) {
                    audioManager.playNextChunk();
                } else {
                    vTaskDelay(pdMS_TO_TICKS(10));
                }
                break;

            default:
                vTaskDelay(pdMS_TO_TICKS(20));
                break;
        }
    }
}

// ============================================================
// Display Task — Runs on Core 1 (secondary priority)
// ============================================================

void displayTask(void* parameter) {
    Serial.println("[Display] Task started on Core 1");

    unsigned long lastFrame = 0;

    while (true) {
        unsigned long now = millis();
        
        if (now - lastFrame >= ANIM_FRAME_MS) {
            lastFrame = now;
            displayManager.update(currentState);
        }

        vTaskDelay(pdMS_TO_TICKS(5));
    }
}

// ============================================================
// WiFi Connection
// ============================================================

void connectWiFi() {
    currentState = STATE_CONNECTING;
    displayManager.showConnecting();
    
    Serial.printf("[WiFi] Connecting to %s...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    
    unsigned long startAttempt = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - startAttempt > WIFI_TIMEOUT_MS) {
            Serial.println("[WiFi] Connection failed!");
            currentState = STATE_ERROR;
            displayManager.showError("WiFi Failed");
            delay(3000);
            ESP.restart();
            return;
        }
        delay(500);
        Serial.print(".");
    }
    
    Serial.printf("\n[WiFi] Connected! IP: %s\n", WiFi.localIP().toString().c_str());
}

// ============================================================
// WebSocket Callbacks
// ============================================================

void onWsStateChange(const char* state) {
    Serial.printf("[WS] State: %s\n", state);
    
    if (strcmp(state, "idle") == 0) {
        currentState = STATE_IDLE;
    } else if (strcmp(state, "listening") == 0) {
        currentState = STATE_LISTENING;
        audioManager.startRecording();
    } else if (strcmp(state, "processing") == 0) {
        currentState = STATE_PROCESSING;
    } else if (strcmp(state, "speaking") == 0) {
        currentState = STATE_SPEAKING;
    }
}

void onWsAudioReceived(uint8_t* data, size_t len) {
    audioManager.queueAudio(data, len);
}

void onWsTextReceived(const char* text, bool done) {
    displayManager.setResponseText(text, done);
}

void onWsTranscript(const char* text) {
    displayManager.setTranscript(text);
    Serial.printf("[WS] Transcript: %s\n", text);
}

void onWsConnected() {
    Serial.println("[WS] Connected to Jarvis server");
    currentState = STATE_IDLE;
    displayManager.showReady();
}

void onWsDisconnected() {
    Serial.println("[WS] Disconnected from server");
    currentState = STATE_ERROR;
    displayManager.showError("Server Lost");
}

// ============================================================
// Setup
// ============================================================

void setup() {
    Serial.begin(SERIAL_BAUD);
    delay(1000);
    
    Serial.println("================================");
    Serial.println("  JARVIS V0.1 — Booting...");
    Serial.println("================================");

    // Initialize display first (for boot animation)
    displayManager.begin();
    displayManager.showBoot();
    
    // Initialize audio subsystem
    audioManager.begin();
    
    // Initialize wake word detector
    wakeWord.begin();

    // Connect WiFi
    connectWiFi();

    // Setup WebSocket callbacks
    wsClient.onStateChange(onWsStateChange);
    wsClient.onAudioReceived(onWsAudioReceived);
    wsClient.onTextReceived(onWsTextReceived);
    wsClient.onTranscript(onWsTranscript);
    wsClient.onConnected(onWsConnected);
    wsClient.onDisconnected(onWsDisconnected);

    // Connect to Jarvis server
    wsClient.begin(WS_HOST, WS_PORT, WS_PATH);
    
    // Start audio task on Core 0 (high priority for real-time audio)
    xTaskCreatePinnedToCore(
        audioTask,
        "AudioTask",
        8192,
        NULL,
        2,  // High priority
        &audioTaskHandle,
        0   // Core 0
    );

    // Start display task on Core 1
    xTaskCreatePinnedToCore(
        displayTask,
        "DisplayTask",
        4096,
        NULL,
        1,  // Lower priority
        &displayTaskHandle,
        1   // Core 1
    );

    Serial.println("[Main] Setup complete");
}

// ============================================================
// Main Loop — WebSocket + State Machine (Core 1)
// ============================================================

void loop() {
    // Handle WebSocket communication
    wsClient.loop();

    // Handle wake word trigger
    if (wakeWordDetected) {
        wakeWordDetected = false;
        
        if (currentState == STATE_IDLE) {
            const char* reason = (lastTriggerType == TRIGGER_CLAP) ? "clap" : "voice";
            Serial.printf("[Main] Activated via %s! Starting listening...\n", reason);
            lastTriggerType = TRIGGER_NONE;
            wsClient.sendWakeWord();
            currentState = STATE_LISTENING;
            audioManager.startRecording();
        }
    }

    // WiFi reconnection
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[Main] WiFi lost, reconnecting...");
        connectWiFi();
        wsClient.reconnect();
    }

    // Audio playback completion check
    if (currentState == STATE_SPEAKING && !audioManager.hasAudioToPlay() && !audioManager.isPlaying()) {
        currentState = STATE_IDLE;
    }

    delay(10);
}
