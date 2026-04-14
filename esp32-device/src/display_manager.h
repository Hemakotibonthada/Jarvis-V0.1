/*
 * Display Manager — Iron Man–style animations for JARVIS on ST7789 TFT.
 *
 * Animations:
 *   - Boot: Expanding rings + "JARVIS" text reveal
 *   - Idle: Breathing arc reactor / pulsing orb
 *   - Listening: Expanding sound wave rings
 *   - Processing: Rotating particle ring with data streams
 *   - Speaking: Audio waveform visualization
 *   - Error: Red alert pulse
 */

#ifndef DISPLAY_MANAGER_H
#define DISPLAY_MANAGER_H

#include <Arduino.h>
#include <TFT_eSPI.h>
#include <math.h>
#include "config.h"

// Colors (RGB565)
#define COLOR_BG        0x0000  // Black
#define COLOR_PRIMARY   0x07FF  // Cyan
#define COLOR_SECONDARY 0x03EF  // Teal
#define COLOR_ACCENT    0xFFE0  // Yellow
#define COLOR_WARNING   0xFD20  // Orange
#define COLOR_ERROR     0xF800  // Red
#define COLOR_SUCCESS   0x07E0  // Green
#define COLOR_DIM       0x0208  // Dark cyan
#define COLOR_TEXT       0xBDF7  // Light gray
#define COLOR_WHITE     0xFFFF

#define CX (SCREEN_WIDTH / 2)
#define CY (SCREEN_HEIGHT / 2)

class DisplayManager {
public:
    void begin() {
        _tft.init();
        _tft.setRotation(0);
        _tft.fillScreen(COLOR_BG);
        
        // Backlight
        pinMode(TFT_BACKLIGHT, OUTPUT);
        digitalWrite(TFT_BACKLIGHT, HIGH);
        
        _frame = 0;
        _lastState = -1;
        _responseText[0] = '\0';
        _transcriptText[0] = '\0';
        _responseDone = false;
        
        // Create sprite for double buffering (reduces flicker)
        _sprite.createSprite(SCREEN_WIDTH, SCREEN_HEIGHT);
        _sprite.setTextDatum(MC_DATUM);
        
        Serial.println("[Display] Initialized (240x240 ST7789)");
    }

    void update(int state) {
        if (state != _lastState) {
            _frame = 0;
            _lastState = state;
        }

        _sprite.fillSprite(COLOR_BG);

        switch (state) {
            case 0: // STATE_BOOT
                _drawBootAnimation();
                break;
            case 1: // STATE_CONNECTING
                _drawConnectingAnimation();
                break;
            case 2: // STATE_IDLE
                _drawIdleAnimation();
                break;
            case 3: // STATE_LISTENING
                _drawListeningAnimation();
                break;
            case 4: // STATE_PROCESSING
                _drawProcessingAnimation();
                break;
            case 5: // STATE_SPEAKING
                _drawSpeakingAnimation();
                break;
            case 6: // STATE_ERROR
                _drawErrorAnimation();
                break;
        }

        _sprite.pushSprite(0, 0);
        _frame++;
    }

    void showBoot() {
        _tft.fillScreen(COLOR_BG);
        _tft.setTextDatum(MC_DATUM);
        _tft.setTextColor(COLOR_PRIMARY);
        _tft.drawString("JARVIS", CX, CY - 10, 4);
        _tft.setTextColor(COLOR_DIM);
        _tft.drawString("V0.1", CX, CY + 20, 2);
    }

    void showConnecting() {
        _tft.fillScreen(COLOR_BG);
        _tft.setTextDatum(MC_DATUM);
        _tft.setTextColor(COLOR_ACCENT);
        _tft.drawString("Connecting...", CX, CY, 2);
    }

    void showReady() {
        // Will be handled by animation loop
    }

    void showError(const char* msg) {
        _tft.fillScreen(COLOR_BG);
        _tft.setTextDatum(MC_DATUM);
        _tft.setTextColor(COLOR_ERROR);
        _tft.drawString("ERROR", CX, CY - 15, 4);
        _tft.setTextColor(COLOR_WARNING);
        _tft.drawString(msg, CX, CY + 15, 2);
    }

    void setResponseText(const char* text, bool done) {
        strlcpy(_responseText, text, sizeof(_responseText));
        _responseDone = done;
    }

    void setTranscript(const char* text) {
        strlcpy(_transcriptText, text, sizeof(_transcriptText));
    }

private:
    TFT_eSPI _tft;
    TFT_eSprite _sprite = TFT_eSprite(&_tft);
    uint32_t _frame;
    int _lastState;
    char _responseText[256];
    char _transcriptText[256];
    bool _responseDone;

    // ---- BOOT ANIMATION ----
    void _drawBootAnimation() {
        float t = _frame * 0.05f;
        
        // Expanding concentric rings
        for (int i = 0; i < 5; i++) {
            float phase = t - i * 0.3f;
            if (phase < 0) continue;
            
            int radius = (int)(phase * 30) % 130;
            uint8_t alpha = max(0, 255 - radius * 2);
            uint16_t color = _blendColor(COLOR_PRIMARY, COLOR_BG, alpha);
            
            _sprite.drawCircle(CX, CY, radius, color);
            if (radius > 2) {
                _sprite.drawCircle(CX, CY, radius - 1, color);
            }
        }

        // JARVIS text with fade-in
        if (_frame > 20) {
            uint8_t textAlpha = min(255, (int)((_frame - 20) * 8));
            uint16_t textColor = _blendColor(COLOR_PRIMARY, COLOR_BG, textAlpha);
            _sprite.setTextColor(textColor);
            _sprite.setTextDatum(MC_DATUM);
            _sprite.drawString("JARVIS", CX, CY - 10, 4);
            
            if (_frame > 40) {
                uint16_t subColor = _blendColor(COLOR_SECONDARY, COLOR_BG, 
                    min(255, (int)((_frame - 40) * 6)));
                _sprite.setTextColor(subColor);
                _sprite.drawString("INITIALIZING", CX, CY + 20, 2);
            }
        }
        
        // Loading bar
        if (_frame > 30) {
            int barWidth = min(160, (int)((_frame - 30) * 3));
            int barX = CX - 80;
            int barY = CY + 50;
            _sprite.drawRect(barX, barY, 160, 8, COLOR_DIM);
            _sprite.fillRect(barX + 1, barY + 1, barWidth - 2, 6, COLOR_PRIMARY);
        }
    }

    // ---- CONNECTING ANIMATION ----
    void _drawConnectingAnimation() {
        float t = _frame * 0.08f;
        
        // Rotating WiFi-like arcs
        for (int i = 0; i < 3; i++) {
            float angle = t + i * 2.094f; // 120 degrees apart
            int r = 30 + i * 20;
            float startAngle = angle - 0.5f;
            float endAngle = angle + 0.5f;
            _drawArc(CX, CY, r, startAngle, endAngle, COLOR_PRIMARY, 2);
        }

        // Center dot
        _sprite.fillCircle(CX, CY, 5, COLOR_PRIMARY);
        
        // Text
        _sprite.setTextColor(COLOR_ACCENT);
        _sprite.setTextDatum(MC_DATUM);
        
        // Animated dots
        int dots = (_frame / 10) % 4;
        char dotStr[8] = "...";
        dotStr[dots] = '\0';
        
        char msg[32];
        snprintf(msg, sizeof(msg), "Connecting%s", dotStr);
        _sprite.drawString(msg, CX, CY + 60, 2);
    }

    // ---- IDLE ANIMATION: Arc Reactor / Breathing Orb ----
    void _drawIdleAnimation() {
        float t = _frame * 0.03f;
        
        // Breathing pulse (sine wave)
        float breath = (sin(t) + 1.0f) * 0.5f; // 0 to 1
        
        // Outer ring segments (Iron Man arc reactor style)
        for (int i = 0; i < 8; i++) {
            float angle = i * 0.785f + t * 0.2f; // 45 deg segments, slow rotate
            float startA = angle - 0.3f;
            float endA = angle + 0.3f;
            
            uint8_t brightness = 80 + (uint8_t)(breath * 100);
            uint16_t color = _blendColor(COLOR_PRIMARY, COLOR_BG, brightness);
            _drawArc(CX, CY, 80 + (int)(breath * 5), startA, endA, color, 3);
        }

        // Middle ring
        int midR = 55 + (int)(breath * 3);
        _sprite.drawCircle(CX, CY, midR, _blendColor(COLOR_SECONDARY, COLOR_BG, 
            100 + (int)(breath * 80)));

        // Inner glow circles
        for (int r = 30; r > 5; r -= 5) {
            uint8_t alpha = (uint8_t)((30 - r) * 4 * (0.5f + breath * 0.5f));
            _sprite.drawCircle(CX, CY, r + (int)(breath * 2), 
                _blendColor(COLOR_PRIMARY, COLOR_BG, alpha));
        }

        // Center bright dot
        int centerR = 8 + (int)(breath * 4);
        _sprite.fillCircle(CX, CY, centerR, COLOR_PRIMARY);
        _sprite.fillCircle(CX, CY, centerR - 2, COLOR_WHITE);

        // Small orbiting particles
        for (int i = 0; i < 4; i++) {
            float pAngle = t * 0.5f + i * 1.571f;
            int px = CX + (int)(65 * cos(pAngle));
            int py = CY + (int)(65 * sin(pAngle));
            _sprite.fillCircle(px, py, 2, COLOR_ACCENT);
        }

        // Status text
        _sprite.setTextColor(COLOR_DIM);
        _sprite.setTextDatum(MC_DATUM);
        _sprite.drawString("JARVIS", CX, CY + 100, 2);
        _sprite.setTextColor(_blendColor(COLOR_SUCCESS, COLOR_BG, 
            100 + (int)(breath * 100)));
        _sprite.drawString("READY", CX, CY + 115, 1);
    }

    // ---- LISTENING ANIMATION: Sound Wave Ripples ----
    void _drawListeningAnimation() {
        float t = _frame * 0.1f;
        
        // Expanding sound wave rings
        for (int i = 0; i < 6; i++) {
            float phase = fmod(t + i * 0.5f, 3.0f);
            int r = (int)(phase * 40);
            
            if (r > 0 && r < 120) {
                uint8_t alpha = max(0, 255 - r * 2);
                uint16_t color = _blendColor(COLOR_SUCCESS, COLOR_BG, alpha);
                _sprite.drawCircle(CX, CY, r, color);
            }
        }

        // Microphone icon (circle + lines)
        _sprite.fillRoundRect(CX - 8, CY - 20, 16, 30, 8, COLOR_SUCCESS);
        _sprite.drawRoundRect(CX - 15, CY - 5, 30, 30, 15, COLOR_SUCCESS);
        _sprite.drawLine(CX, CY + 25, CX, CY + 35, COLOR_SUCCESS);
        _sprite.drawLine(CX - 8, CY + 35, CX + 8, CY + 35, COLOR_SUCCESS);

        // Audio level bars
        for (int i = -3; i <= 3; i++) {
            int x = CX + i * 12;
            int h = random(10, 35);
            int y = CY + 55;
            _sprite.fillRect(x - 3, y, 6, h, 
                _blendColor(COLOR_SUCCESS, COLOR_PRIMARY, random(100, 255)));
        }

        // "Listening..." text
        _sprite.setTextColor(COLOR_SUCCESS);
        _sprite.setTextDatum(MC_DATUM);
        _sprite.drawString("Listening", CX, CY + 100, 2);
        
        // Transcript text if available
        if (_transcriptText[0] != '\0') {
            _sprite.setTextColor(COLOR_TEXT);
            _sprite.drawString(_transcriptText, CX, CY - 70, 1);
        }
    }

    // ---- PROCESSING ANIMATION: Rotating Data Ring ----
    void _drawProcessingAnimation() {
        float t = _frame * 0.08f;
        
        // Outer rotating ring of particles
        for (int i = 0; i < 24; i++) {
            float angle = i * 0.2618f + t; // 15 deg + rotation
            int r = 75;
            int px = CX + (int)(r * cos(angle));
            int py = CY + (int)(r * sin(angle));
            
            // Particle size varies
            int size = 2 + (int)(sin(angle * 3 + t) * 2);
            uint16_t color = (i % 3 == 0) ? COLOR_ACCENT : COLOR_PRIMARY;
            _sprite.fillCircle(px, py, max(1, size), color);
        }

        // Inner counter-rotating ring
        for (int i = 0; i < 16; i++) {
            float angle = -t * 1.5f + i * 0.3927f;
            int r = 45;
            int px = CX + (int)(r * cos(angle));
            int py = CY + (int)(r * sin(angle));
            _sprite.fillCircle(px, py, 2, COLOR_SECONDARY);
        }

        // Center spinning hexagon
        float hexRot = t * 0.5f;
        for (int i = 0; i < 6; i++) {
            float a1 = hexRot + i * 1.047f;
            float a2 = hexRot + (i + 1) * 1.047f;
            int x1 = CX + (int)(20 * cos(a1));
            int y1 = CY + (int)(20 * sin(a1));
            int x2 = CX + (int)(20 * cos(a2));
            int y2 = CY + (int)(20 * sin(a2));
            _sprite.drawLine(x1, y1, x2, y2, COLOR_PRIMARY);
        }

        // Scanning lines
        for (int i = 0; i < 3; i++) {
            float scanAngle = t * 2 + i * 2.094f;
            int sx = CX + (int)(90 * cos(scanAngle));
            int sy = CY + (int)(90 * sin(scanAngle));
            _sprite.drawLine(CX, CY, sx, sy, 
                _blendColor(COLOR_PRIMARY, COLOR_BG, 60));
        }

        // "Processing" text with animated dots
        int dots = (_frame / 8) % 4;
        char msg[20];
        snprintf(msg, sizeof(msg), "Thinking");
        for (int i = 0; i < dots; i++) {
            msg[8 + i] = '.';
            msg[9 + i] = '\0';
        }
        
        _sprite.setTextColor(COLOR_ACCENT);
        _sprite.setTextDatum(MC_DATUM);
        _sprite.drawString(msg, CX, CY + 100, 2);
    }

    // ---- SPEAKING ANIMATION: Audio Waveform ----
    void _drawSpeakingAnimation() {
        float t = _frame * 0.12f;
        
        // Central pulsing orb
        float pulse = (sin(t * 2) + 1) * 0.5f;
        int orbR = 25 + (int)(pulse * 15);
        _sprite.fillCircle(CX, CY, orbR, COLOR_PRIMARY);
        _sprite.fillCircle(CX, CY, orbR - 4, _blendColor(COLOR_PRIMARY, COLOR_WHITE, 180));

        // Sound wave visualization
        for (int i = 0; i < SCREEN_WIDTH; i += 2) {
            float x = (i - CX) * 0.05f;
            
            // Multiple wave components for richness
            float y = sin(x * 2 + t) * 20 * pulse;
            y += sin(x * 3.7f - t * 0.7f) * 10 * pulse;
            y += sin(x * 5.3f + t * 1.3f) * 5 * pulse;
            
            int py = CY + (int)y;
            int prevPy = CY + (int)(sin((x - 0.1f) * 2 + t) * 20 * pulse +
                                    sin((x - 0.1f) * 3.7f - t * 0.7f) * 10 * pulse);
            
            // Gradient from center
            int dist = abs(i - CX);
            uint8_t alpha = max(0, 255 - dist * 2);
            uint16_t color = _blendColor(COLOR_PRIMARY, COLOR_BG, alpha);
            
            _sprite.drawPixel(i, py, color);
            if (i > 0) {
                _sprite.drawLine(i - 2, prevPy, i, py, color);
            }
        }

        // Outer glow rings
        for (int r = orbR + 10; r < orbR + 40; r += 8) {
            uint8_t alpha = max(0, 200 - (r - orbR) * 5);
            _sprite.drawCircle(CX, CY, r, 
                _blendColor(COLOR_PRIMARY, COLOR_BG, (uint8_t)(alpha * pulse)));
        }

        // Response text at bottom
        if (_responseText[0] != '\0') {
            _sprite.setTextColor(COLOR_TEXT);
            _sprite.setTextDatum(MC_DATUM);
            // Wrap text to fit display
            _drawWrappedText(_responseText, CX, 180, 220, 1);
        }

        // "Speaking" label
        _sprite.setTextColor(COLOR_PRIMARY);
        _sprite.setTextDatum(MC_DATUM);
        _sprite.drawString("Speaking", CX, 20, 2);
    }

    // ---- ERROR ANIMATION ----
    void _drawErrorAnimation() {
        float t = _frame * 0.15f;
        float pulse = (sin(t * 3) + 1) * 0.5f;

        // Red pulsing background glow
        for (int r = 80; r > 10; r -= 5) {
            uint8_t alpha = (uint8_t)((80 - r) * pulse * 3);
            _sprite.drawCircle(CX, CY, r, _blendColor(COLOR_ERROR, COLOR_BG, alpha));
        }

        // Warning triangle
        int triSize = 40;
        int triY = CY - 10;
        _sprite.drawLine(CX, triY - triSize, CX - triSize, triY + triSize, COLOR_ERROR);
        _sprite.drawLine(CX - triSize, triY + triSize, CX + triSize, triY + triSize, COLOR_ERROR);
        _sprite.drawLine(CX + triSize, triY + triSize, CX, triY - triSize, COLOR_ERROR);

        // Exclamation mark
        _sprite.fillRect(CX - 3, triY - 15, 6, 25, COLOR_ERROR);
        _sprite.fillCircle(CX, triY + 20, 4, COLOR_ERROR);

        // Error text
        _sprite.setTextColor(COLOR_ERROR);
        _sprite.setTextDatum(MC_DATUM);
        _sprite.drawString("ERROR", CX, CY + 60, 4);
    }

    // ---- UTILITY FUNCTIONS ----

    uint16_t _blendColor(uint16_t fg, uint16_t bg, uint8_t alpha) {
        // Extract RGB565 components
        uint8_t fgR = (fg >> 11) & 0x1F;
        uint8_t fgG = (fg >> 5) & 0x3F;
        uint8_t fgB = fg & 0x1F;
        uint8_t bgR = (bg >> 11) & 0x1F;
        uint8_t bgG = (bg >> 5) & 0x3F;
        uint8_t bgB = bg & 0x1F;

        // Blend
        uint8_t r = (fgR * alpha + bgR * (255 - alpha)) / 255;
        uint8_t g = (fgG * alpha + bgG * (255 - alpha)) / 255;
        uint8_t b = (fgB * alpha + bgB * (255 - alpha)) / 255;

        return (r << 11) | (g << 5) | b;
    }

    void _drawArc(int cx, int cy, int r, float startAngle, float endAngle, 
                  uint16_t color, int thickness) {
        float step = 0.02f;
        for (float a = startAngle; a <= endAngle; a += step) {
            int x = cx + (int)(r * cos(a));
            int y = cy + (int)(r * sin(a));
            if (thickness <= 1) {
                _sprite.drawPixel(x, y, color);
            } else {
                _sprite.fillCircle(x, y, thickness / 2, color);
            }
        }
    }

    void _drawWrappedText(const char* text, int x, int y, int maxWidth, int font) {
        char line[40];
        int len = strlen(text);
        int lineStart = 0;
        int lineY = y;
        int maxLines = 3;
        int lineCount = 0;

        while (lineStart < len && lineCount < maxLines) {
            int lineEnd = min(lineStart + 35, len);
            // Find word boundary
            if (lineEnd < len) {
                int lastSpace = lineEnd;
                while (lastSpace > lineStart && text[lastSpace] != ' ') lastSpace--;
                if (lastSpace > lineStart) lineEnd = lastSpace;
            }
            
            int copyLen = min(lineEnd - lineStart, (int)sizeof(line) - 1);
            strncpy(line, text + lineStart, copyLen);
            line[copyLen] = '\0';
            
            _sprite.drawString(line, x, lineY, font);
            lineY += 14;
            lineStart = lineEnd;
            while (lineStart < len && text[lineStart] == ' ') lineStart++;
            lineCount++;
        }
    }
};

#endif // DISPLAY_MANAGER_H
