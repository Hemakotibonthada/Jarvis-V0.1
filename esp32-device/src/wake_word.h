/*
 * Wake Word & Clap Detector — Dual activation for JARVIS on ESP32.
 *
 * Activation methods:
 *   1. Voice wake word ("Jarvis") — energy + zero-crossing voiced speech detection
 *   2. Double clap — two sharp transient impulses within a short window
 *
 * Clap detection algorithm:
 *   - Claps are characterized by sharp energy spikes (high amplitude, very short)
 *   - High zero-crossing rate (broadband noise, not tonal like speech)
 *   - Two claps within 200-700ms qualify as a double-clap trigger
 */

#ifndef WAKE_WORD_H
#define WAKE_WORD_H

#include <Arduino.h>
#include "config.h"

enum WakeTrigger {
    TRIGGER_NONE,
    TRIGGER_VOICE,
    TRIGGER_CLAP
};

class WakeWordDetector {
public:
    void begin() {
        _lastTrigger = 0;
        _energyHistory[0] = 0;
        _historyIndex = 0;
        _cooldownMs = 2000;  // 2 second cooldown between triggers

        // Clap state
        _firstClapTime = 0;
        _waitingSecondClap = false;
        _clapCooldown = 0;

        Serial.println("[WakeWord] Initialized (voice + clap detector)");
    }

    /**
     * Detect activation from audio samples.
     * Returns TRIGGER_VOICE, TRIGGER_CLAP, or TRIGGER_NONE.
     */
    WakeTrigger detect(int16_t* samples, size_t count) {
        if (count == 0) return TRIGGER_NONE;

        unsigned long now = millis();

        // Global cooldown
        if (now - _lastTrigger < _cooldownMs) {
            return TRIGGER_NONE;
        }

        // Calculate frame energy (RMS) and zero-crossing rate
        int64_t sumSquares = 0;
        int zeroCrossings = 0;
        int16_t peakAmplitude = 0;

        for (size_t i = 0; i < count; i++) {
            sumSquares += (int64_t)samples[i] * samples[i];
            int16_t absVal = abs(samples[i]);
            if (absVal > peakAmplitude) peakAmplitude = absVal;
            if (i > 0) {
                if ((samples[i] > 0 && samples[i-1] < 0) ||
                    (samples[i] < 0 && samples[i-1] > 0)) {
                    zeroCrossings++;
                }
            }
        }

        float energy = sqrt((float)sumSquares / count);
        float zcRate = (float)zeroCrossings / count;
        float crestFactor = (energy > 0) ? (float)peakAmplitude / energy : 0;

        // Update energy history for adaptive threshold
        _energyHistory[_historyIndex] = energy;
        _historyIndex = (_historyIndex + 1) % HISTORY_SIZE;
        _frameCount++;

        if (_frameCount < HISTORY_SIZE) return TRIGGER_NONE;

        float bgNoise = _getMedianEnergy();

        // ---- CLAP DETECTION ----
        // Claps have: very high crest factor (spiky), high ZCR (broadband),
        // and energy well above background
        bool isClap = (crestFactor > CLAP_CREST_THRESHOLD) &&
                      (zcRate > CLAP_ZCR_MIN) &&
                      (energy > bgNoise * CLAP_ENERGY_RATIO) &&
                      (energy > CLAP_MIN_ENERGY) &&
                      (now > _clapCooldown);

        if (isClap) {
            if (_waitingSecondClap) {
                unsigned long gap = now - _firstClapTime;
                if (gap >= CLAP_MIN_GAP_MS && gap <= CLAP_MAX_GAP_MS) {
                    // Double clap detected!
                    _waitingSecondClap = false;
                    _lastTrigger = now;
                    _clapCooldown = now + 500;  // short cooldown after trigger
                    Serial.printf("[WakeWord] DOUBLE CLAP! gap=%lums, energy=%.0f, crest=%.1f\n",
                                 gap, energy, crestFactor);
                    return TRIGGER_CLAP;
                } else if (gap > CLAP_MAX_GAP_MS) {
                    // Too slow — treat as new first clap
                    _firstClapTime = now;
                    _clapCooldown = now + 80;  // debounce
                    Serial.printf("[WakeWord] Clap 1 (reset), energy=%.0f\n", energy);
                }
                // else gap < CLAP_MIN_GAP_MS — ignore (echo/bounce)
            } else {
                // First clap
                _firstClapTime = now;
                _waitingSecondClap = true;
                _clapCooldown = now + 80;  // debounce
                Serial.printf("[WakeWord] Clap 1, energy=%.0f, crest=%.1f\n", energy, crestFactor);
            }
        }

        // Expire first clap if second doesn't come in time
        if (_waitingSecondClap && (now - _firstClapTime > CLAP_MAX_GAP_MS)) {
            _waitingSecondClap = false;
        }

        // ---- VOICE WAKE WORD DETECTION ----
        bool energySufficient = energy > bgNoise * 3.0f && energy > WAKE_ENERGY_THRESHOLD;
        bool isVoicedSpeech = zcRate > 0.05f && zcRate < 0.5f;

        if (energySufficient && isVoicedSpeech) {
            _speechFrames++;
            if (_speechFrames >= MIN_SPEECH_FRAMES) {
                _speechFrames = 0;
                _lastTrigger = now;
                Serial.printf("[WakeWord] VOICE trigger! Energy: %.0f (bg: %.0f), ZCR: %.3f\n",
                             energy, bgNoise, zcRate);
                return TRIGGER_VOICE;
            }
        } else {
            if (_speechFrames > 0) _speechFrames--;
        }

        return TRIGGER_NONE;
    }

    // Legacy compatibility — returns true for any trigger
    bool detectAny(int16_t* samples, size_t count) {
        return detect(samples, count) != TRIGGER_NONE;
    }

    void setCooldown(unsigned long ms) {
        _cooldownMs = ms;
    }

    void reset() {
        _speechFrames = 0;
        _frameCount = 0;
        _historyIndex = 0;
        _waitingSecondClap = false;
    }

private:
    static const int HISTORY_SIZE = 50;
    static const int MIN_SPEECH_FRAMES = 3;

    float _energyHistory[HISTORY_SIZE];
    int _historyIndex;
    unsigned long _lastTrigger;
    unsigned long _cooldownMs;
    int _speechFrames = 0;
    int _frameCount = 0;

    // Clap state
    unsigned long _firstClapTime;
    bool _waitingSecondClap;
    unsigned long _clapCooldown;

    float _getMedianEnergy() {
        float sorted[HISTORY_SIZE];
        memcpy(sorted, _energyHistory, sizeof(sorted));

        // Partial sort to find ~25th percentile (noise floor)
        for (int i = 0; i < HISTORY_SIZE / 4; i++) {
            for (int j = i + 1; j < HISTORY_SIZE; j++) {
                if (sorted[j] < sorted[i]) {
                    float tmp = sorted[i];
                    sorted[i] = sorted[j];
                    sorted[j] = tmp;
                }
            }
        }

        return sorted[HISTORY_SIZE / 4];
    }
};

#endif // WAKE_WORD_H
