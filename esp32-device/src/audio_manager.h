/*
 * Audio Manager — I2S microphone input and speaker output for ESP32.
 * Handles INMP441 mic capture and MAX98357A DAC playback.
 */

#ifndef AUDIO_MANAGER_H
#define AUDIO_MANAGER_H

#include <Arduino.h>
#include <driver/i2s.h>
#include <freertos/queue.h>
#include "config.h"

#define AUDIO_QUEUE_SIZE    20
#define AUDIO_QUEUE_ITEM_SIZE AUDIO_SEND_CHUNK

class AudioManager {
public:
    void begin() {
        _setupMicrophone();
        _setupSpeaker();
        
        // Create audio playback queue
        _playQueue = xQueueCreate(AUDIO_QUEUE_SIZE, sizeof(AudioChunk));
        
        _silenceStart = 0;
        _recordStart = 0;
        _isRecording = false;
        _isPlaying = false;
        
        Serial.println("[Audio] Initialized");
    }

    // ----- Microphone -----

    size_t readMic(int16_t* buffer, size_t samples) {
        size_t bytesRead = 0;
        esp_err_t result = i2s_read(
            I2S_MIC_PORT,
            buffer,
            samples * sizeof(int16_t),
            &bytesRead,
            pdMS_TO_TICKS(100)
        );
        
        if (result != ESP_OK) {
            return 0;
        }
        return bytesRead;
    }

    bool isSilence(int16_t* samples, size_t count) {
        if (count == 0) return true;
        
        // Calculate RMS energy
        int64_t sum = 0;
        for (size_t i = 0; i < count; i++) {
            sum += (int64_t)samples[i] * samples[i];
        }
        uint32_t rms = sqrt((double)sum / count);
        
        return rms < VAD_THRESHOLD;
    }

    void startRecording() {
        _isRecording = true;
        _recordStart = millis();
        _silenceStart = millis();
        // Flush mic buffer
        int16_t dummy[256];
        size_t bytesRead;
        i2s_read(I2S_MIC_PORT, dummy, sizeof(dummy), &bytesRead, pdMS_TO_TICKS(10));
        Serial.println("[Audio] Recording started");
    }

    void stopRecording() {
        _isRecording = false;
        Serial.println("[Audio] Recording stopped");
    }

    void resetSilenceTimer() {
        _silenceStart = millis();
    }

    unsigned long getSilenceDuration() {
        return millis() - _silenceStart;
    }

    unsigned long getRecordingDuration() {
        return millis() - _recordStart;
    }

    // ----- Speaker -----

    struct AudioChunk {
        uint8_t data[AUDIO_SEND_CHUNK];
        size_t length;
    };

    void queueAudio(uint8_t* data, size_t len) {
        // Split incoming data into queue-sized chunks
        size_t offset = 0;
        while (offset < len) {
            AudioChunk chunk;
            chunk.length = min(len - offset, (size_t)AUDIO_SEND_CHUNK);
            memcpy(chunk.data, data + offset, chunk.length);
            
            if (xQueueSend(_playQueue, &chunk, pdMS_TO_TICKS(100)) != pdTRUE) {
                Serial.println("[Audio] Play queue full, dropping chunk");
            }
            offset += chunk.length;
        }
    }

    void playNextChunk() {
        AudioChunk chunk;
        if (xQueueReceive(_playQueue, &chunk, pdMS_TO_TICKS(50)) == pdTRUE) {
            _isPlaying = true;
            size_t bytesWritten = 0;
            
            i2s_write(
                I2S_SPK_PORT,
                chunk.data,
                chunk.length,
                &bytesWritten,
                pdMS_TO_TICKS(200)
            );
        } else {
            _isPlaying = false;
        }
    }

    bool hasAudioToPlay() {
        return uxQueueMessagesWaiting(_playQueue) > 0;
    }

    bool isPlaying() {
        return _isPlaying;
    }

    bool isRecording() {
        return _isRecording;
    }

private:
    QueueHandle_t _playQueue;
    unsigned long _silenceStart;
    unsigned long _recordStart;
    volatile bool _isRecording;
    volatile bool _isPlaying;

    void _setupMicrophone() {
        i2s_config_t mic_config = {
            .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX),
            .sample_rate = SAMPLE_RATE,
            .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
            .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
            .communication_format = I2S_COMM_FORMAT_STAND_I2S,
            .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
            .dma_buf_count = 8,
            .dma_buf_len = AUDIO_BUFFER_SIZE,
            .use_apll = false,
            .tx_desc_auto_clear = false,
            .fixed_mclk = 0,
        };

        i2s_pin_config_t mic_pins = {
            .bck_io_num = I2S_MIC_SCK,
            .ws_io_num = I2S_MIC_WS,
            .data_out_num = I2S_PIN_NO_CHANGE,
            .data_in_num = I2S_MIC_SD,
        };

        esp_err_t err = i2s_driver_install(I2S_MIC_PORT, &mic_config, 0, NULL);
        if (err != ESP_OK) {
            Serial.printf("[Audio] Mic I2S install failed: %d\n", err);
            return;
        }
        i2s_set_pin(I2S_MIC_PORT, &mic_pins);
        i2s_zero_dma_buffer(I2S_MIC_PORT);
        Serial.println("[Audio] Microphone initialized");
    }

    void _setupSpeaker() {
        i2s_config_t spk_config = {
            .mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX),
            .sample_rate = SAMPLE_RATE,
            .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
            .channel_format = I2S_CHANNEL_FMT_ONLY_LEFT,
            .communication_format = I2S_COMM_FORMAT_STAND_I2S,
            .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
            .dma_buf_count = 8,
            .dma_buf_len = AUDIO_BUFFER_SIZE,
            .use_apll = false,
            .tx_desc_auto_clear = true,
            .fixed_mclk = 0,
        };

        i2s_pin_config_t spk_pins = {
            .bck_io_num = I2S_SPK_BCK,
            .ws_io_num = I2S_SPK_WS,
            .data_out_num = I2S_SPK_DATA,
            .data_in_num = I2S_PIN_NO_CHANGE,
        };

        esp_err_t err = i2s_driver_install(I2S_SPK_PORT, &spk_config, 0, NULL);
        if (err != ESP_OK) {
            Serial.printf("[Audio] Speaker I2S install failed: %d\n", err);
            return;
        }
        i2s_set_pin(I2S_SPK_PORT, &spk_pins);
        i2s_zero_dma_buffer(I2S_SPK_PORT);
        Serial.println("[Audio] Speaker initialized");
    }
};

#endif // AUDIO_MANAGER_H
