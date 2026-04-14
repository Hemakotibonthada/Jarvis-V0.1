#ifndef CONFIG_H
#define CONFIG_H

// ============================================================
// JARVIS ESP32 Device Configuration
// ============================================================

// ----- WiFi -----
#define WIFI_SSID       "YOUR_WIFI_SSID"
#define WIFI_PASSWORD   "YOUR_WIFI_PASSWORD"
#define WIFI_TIMEOUT_MS 15000

// ----- WebSocket Server -----
#define WS_HOST         "192.168.1.100"  // IP of Python server
#define WS_PORT         8765
#define WS_PATH         "/"
#define WS_RECONNECT_MS 3000

// ----- Audio: I2S Microphone (INMP441) -----
#ifndef I2S_MIC_SCK
#define I2S_MIC_SCK     26
#endif
#ifndef I2S_MIC_WS
#define I2S_MIC_WS      25
#endif
#ifndef I2S_MIC_SD
#define I2S_MIC_SD      33
#endif
#define I2S_MIC_PORT    I2S_NUM_0

// ----- Audio: I2S Speaker (MAX98357A) -----
#ifndef I2S_SPK_BCK
#define I2S_SPK_BCK     27
#endif
#ifndef I2S_SPK_WS
#define I2S_SPK_WS      14
#endif
#ifndef I2S_SPK_DATA
#define I2S_SPK_DATA    12
#endif
#define I2S_SPK_PORT    I2S_NUM_1

// ----- Audio Settings -----
#define SAMPLE_RATE     16000
#define SAMPLE_BITS     16
#define MIC_CHANNELS    1
#define AUDIO_BUFFER_SIZE 1024
#define AUDIO_SEND_CHUNK  4096

// ----- VAD (Voice Activity Detection) -----
#define VAD_THRESHOLD       800     // Amplitude threshold
#define VAD_SILENCE_MS      1500    // ms of silence to stop recording
#define VAD_MIN_SPEECH_MS   300     // Min speech duration
#define VAD_MAX_RECORD_MS   30000   // Max recording duration

// ----- Display (ST7789 240x240) -----
#define SCREEN_WIDTH    240
#define SCREEN_HEIGHT   240
#define TFT_BACKLIGHT   4

// ----- Wake Word -----
#define WAKE_WORD_ENABLED   true
#define WAKE_ENERGY_THRESHOLD 1000

// ----- Clap Detection -----
#define CLAP_ENABLED        true
#define CLAP_CREST_THRESHOLD 4.0f    // Peak/RMS ratio (claps are very spiky)
#define CLAP_ZCR_MIN        0.3f    // Min zero-crossing rate (broadband noise)
#define CLAP_ENERGY_RATIO   5.0f    // Energy must be 5x background noise
#define CLAP_MIN_ENERGY     1500    // Absolute min energy for a clap
#define CLAP_MIN_GAP_MS     150     // Min gap between two claps (ms)
#define CLAP_MAX_GAP_MS     700     // Max gap between two claps (ms)

// ----- LED (optional WS2812B ring) -----
#define LED_PIN         15
#define LED_COUNT       12

// ----- Animation -----
#define ANIM_FPS        30
#define ANIM_FRAME_MS   (1000 / ANIM_FPS)

// ----- System -----
#define SERIAL_BAUD     115200
#define STATUS_LED_PIN  2

#endif // CONFIG_H
