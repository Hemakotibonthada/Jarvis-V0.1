# ESP32 Hardware Wiring Guide

## Components
- ESP32-S3 DevKit (or ESP32 WROOM-32)
- INMP441 I2S MEMS Microphone
- MAX98357A I2S Amplifier
- ST7789 1.3" TFT Display (240x240, SPI)
- 3W 4Ω Speaker
- Optional: WS2812B LED Ring (12 LEDs)

---

## Wiring Diagram

### ESP32 WROOM-32 Pinout

```
                 ┌────────────────────┐
                 │    ESP32 WROOM     │
                 │                    │
      INMP441 ──►│ GPIO26 (I2S_SCK)  │
      (Mic)   ──►│ GPIO25 (I2S_WS)   │
              ──►│ GPIO33 (I2S_SD)   │
                 │                    │
    MAX98357A ──►│ GPIO27 (I2S_BCK)  │
    (Speaker) ──►│ GPIO14 (I2S_WS)   │
              ──►│ GPIO12 (I2S_DATA) │
                 │                    │
      ST7789  ──►│ GPIO18 (SPI_CLK)  │
     (Display)──►│ GPIO23 (SPI_MOSI) │
              ──►│ GPIO5  (CS)       │
              ──►│ GPIO16 (DC)       │
              ──►│ GPIO17 (RST)      │
              ──►│ GPIO4  (BL)       │
                 │                    │
    WS2812B   ──►│ GPIO15 (LED_DATA) │
    (Optional)   │                    │
     Status   ──►│ GPIO2  (LED)      │
                 │                    │
                 │ 3V3 ──► VCC (all) │
                 │ GND ──► GND (all) │
                 └────────────────────┘
```

### INMP441 Microphone Wiring
```
INMP441     ESP32
-------     -----
VDD    ──── 3.3V
GND    ──── GND
SD     ──── GPIO33 (Data In)
WS     ──── GPIO25 (Word Select / LRCLK)
SCK    ──── GPIO26 (Serial Clock)
L/R    ──── GND (Left channel)
```

### MAX98357A Amplifier Wiring
```
MAX98357A   ESP32
---------   -----
VIN    ──── 5V (USB VBUS)
GND    ──── GND
DIN    ──── GPIO12 (Data Out)
BCLK   ──── GPIO27 (Bit Clock)
LRC    ──── GPIO14 (Word Select)
GAIN   ──── (leave floating = 9dB, or GND = 3dB)
SD     ──── (leave floating or pull HIGH to enable)
```

### ST7789 Display Wiring
```
ST7789      ESP32
------      -----
VCC    ──── 3.3V
GND    ──── GND
SCL    ──── GPIO18 (SPI Clock)
SDA    ──── GPIO23 (SPI MOSI)
CS     ──── GPIO5
DC     ──── GPIO16
RST    ──── GPIO17
BLK    ──── GPIO4  (Backlight)
```

### Optional: WS2812B LED Ring
```
WS2812B     ESP32
-------     -----
VCC    ──── 5V
GND    ──── GND
DIN    ──── GPIO15 (through 330Ω resistor)
```

---

## ESP32-S3 Pinout (Alternative)

If using ESP32-S3, the pin assignments change:

```
INMP441:  SCK=GPIO42, WS=GPIO41, SD=GPIO2
MAX98357: BCK=GPIO17, WS=GPIO18, DATA=GPIO16
ST7789:   Same as above (SPI)
```

---

## Power Notes
- ESP32 draws ~240mA during WiFi + processing
- MAX98357A draws ~100mA at full volume
- Total: ~400-500mA — use a good USB cable
- For battery: LiPo 3.7V 2000mAh + TP4056 charger

## Assembly Tips
1. Wire the display first and test animations
2. Add microphone — test with Serial monitor
3. Add speaker — test with tone generation
4. Connect WiFi and test WebSocket
5. Flash final firmware
