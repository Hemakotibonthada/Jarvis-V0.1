/*
 * WebSocket Client — Connects ESP32 to Jarvis Python server.
 * Handles binary (audio) and text (JSON) message protocols.
 *
 * Protocol:
 *   Binary messages:
 *     0x01 + data = audio chunk
 *     0x02 = recording started
 *     0x03 = recording ended
 *   Text messages: JSON with "type" field
 */

#ifndef WS_CLIENT_H
#define WS_CLIENT_H

#include <Arduino.h>
#include <WebSocketsClient.h>
#include <ArduinoJson.h>
#include "config.h"

typedef void (*StateCallback)(const char* state);
typedef void (*AudioCallback)(uint8_t* data, size_t len);
typedef void (*TextCallback)(const char* text, bool done);
typedef void (*TranscriptCallback)(const char* text);
typedef void (*VoidCallback)();

class WSClient {
public:
    void begin(const char* host, uint16_t port, const char* path) {
        _host = host;
        _port = port;
        _path = path;
        
        _ws.begin(host, port, path);
        _ws.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
            _handleEvent(type, payload, length);
        });
        _ws.setReconnectInterval(WS_RECONNECT_MS);
        
        Serial.printf("[WS] Connecting to ws://%s:%d%s\n", host, port, path);
    }

    void loop() {
        _ws.loop();
    }

    void reconnect() {
        _ws.begin(_host, _port, _path);
    }

    // ----- Send Methods -----

    void sendAudioChunk(uint8_t* data, size_t len) {
        if (!_connected) return;
        
        // Prepend 0x01 marker byte
        uint8_t* packet = (uint8_t*)malloc(len + 1);
        if (!packet) return;
        
        packet[0] = 0x01;
        memcpy(packet + 1, data, len);
        _ws.sendBIN(packet, len + 1);
        free(packet);
    }

    void sendRecordingStart() {
        if (!_connected) return;
        uint8_t marker = 0x02;
        _ws.sendBIN(&marker, 1);
        Serial.println("[WS] Sent: Recording start");
    }

    void sendRecordingEnd() {
        if (!_connected) return;
        uint8_t marker = 0x03;
        _ws.sendBIN(&marker, 1);
        Serial.println("[WS] Sent: Recording end");
    }

    void sendWakeWord() {
        if (!_connected) return;
        
        JsonDocument doc;
        doc["type"] = "wake_word";
        
        char buffer[64];
        serializeJson(doc, buffer);
        _ws.sendTXT(buffer);
        
        // Also signal recording start
        sendRecordingStart();
        Serial.println("[WS] Sent: Wake word");
    }

    void sendTextInput(const char* text) {
        if (!_connected) return;
        
        JsonDocument doc;
        doc["type"] = "text_input";
        doc["text"] = text;
        
        char buffer[512];
        serializeJson(doc, buffer);
        _ws.sendTXT(buffer);
    }

    void sendCancel() {
        if (!_connected) return;
        
        JsonDocument doc;
        doc["type"] = "cancel";
        
        char buffer[32];
        serializeJson(doc, buffer);
        _ws.sendTXT(buffer);
    }

    // ----- Callbacks -----

    void onStateChange(StateCallback cb) { _onState = cb; }
    void onAudioReceived(AudioCallback cb) { _onAudio = cb; }
    void onTextReceived(TextCallback cb) { _onText = cb; }
    void onTranscript(TranscriptCallback cb) { _onTranscript = cb; }
    void onConnected(VoidCallback cb) { _onConnected = cb; }
    void onDisconnected(VoidCallback cb) { _onDisconnected = cb; }

    bool isConnected() { return _connected; }

private:
    WebSocketsClient _ws;
    bool _connected = false;
    const char* _host;
    uint16_t _port;
    const char* _path;

    // Callbacks
    StateCallback _onState = nullptr;
    AudioCallback _onAudio = nullptr;
    TextCallback _onText = nullptr;
    TranscriptCallback _onTranscript = nullptr;
    VoidCallback _onConnected = nullptr;
    VoidCallback _onDisconnected = nullptr;

    void _handleEvent(WStype_t type, uint8_t* payload, size_t length) {
        switch (type) {
            case WStype_DISCONNECTED:
                _connected = false;
                Serial.println("[WS] Disconnected");
                if (_onDisconnected) _onDisconnected();
                break;

            case WStype_CONNECTED:
                _connected = true;
                Serial.printf("[WS] Connected to: %s\n", payload);
                if (_onConnected) _onConnected();
                break;

            case WStype_TEXT:
                _handleTextMessage((char*)payload, length);
                break;

            case WStype_BIN:
                _handleBinaryMessage(payload, length);
                break;

            case WStype_PING:
                // Auto-handled by library
                break;

            case WStype_PONG:
                break;

            case WStype_ERROR:
                Serial.printf("[WS] Error: %s\n", payload);
                break;

            default:
                break;
        }
    }

    void _handleTextMessage(char* payload, size_t length) {
        JsonDocument doc;
        DeserializationError error = deserializeJson(doc, payload, length);
        
        if (error) {
            Serial.printf("[WS] JSON parse error: %s\n", error.c_str());
            return;
        }

        const char* msgType = doc["type"] | "";

        if (strcmp(msgType, "state") == 0) {
            const char* state = doc["state"] | "idle";
            Serial.printf("[WS] State -> %s\n", state);
            if (_onState) _onState(state);
        }
        else if (strcmp(msgType, "response_text") == 0) {
            const char* text = doc["text"] | "";
            bool done = doc["done"] | false;
            if (_onText) _onText(text, done);
        }
        else if (strcmp(msgType, "transcript") == 0) {
            const char* text = doc["text"] | "";
            if (_onTranscript) _onTranscript(text);
        }
        else if (strcmp(msgType, "welcome") == 0) {
            const char* msg = doc["message"] | "Connected";
            Serial.printf("[WS] Welcome: %s\n", msg);
        }
        else if (strcmp(msgType, "action") == 0) {
            const char* action = doc["action"] | "";
            Serial.printf("[WS] Action: %s\n", action);
        }
        else if (strcmp(msgType, "error") == 0) {
            const char* errMsg = doc["message"] | "Unknown error";
            Serial.printf("[WS] Server error: %s\n", errMsg);
        }
    }

    void _handleBinaryMessage(uint8_t* payload, size_t length) {
        if (length < 1) return;

        uint8_t marker = payload[0];
        
        if (marker == 0x01) {
            // Audio data
            if (_onAudio && length > 1) {
                _onAudio(payload + 1, length - 1);
            }
        }
    }
};

#endif // WS_CLIENT_H
