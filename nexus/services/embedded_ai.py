"""Embedded Engineering Knowledge Engine — zero-cost AI fallback.

Provides accurate, curated IoT/electronics answers without any API key.
Used when no online provider is configured or when provider fails.
Responses are clearly marked as knowledge-base answers (not AI-generated).
"""
from __future__ import annotations
import re
from typing import Iterator

# --------------------------------------------------------------------------- #
# Curated knowledge topics                                                     #
# --------------------------------------------------------------------------- #

_PINOUTS = {
    'esp32': """**ESP32 DevKit V1 Pinout (ESP32-WROOM-32)**
- **Power**: VIN (5V in), 3V3 (out), GND
- **I2C**: SDA=GPIO21, SCL=GPIO22
- **SPI**: SCK=GPIO18, MISO=GPIO19, MOSI=GPIO23
- **UART**: RX=GPIO16, TX=GPIO17
- **Analog (ADC1)**: GPIO32, 33, 34, 35
- **PWM-capable**: GPIO4, 16, 17, 25, 26, 27, 32, 33
- ⚠️ GPIO34, 35, 36, 39 are INPUT ONLY (no output/pullup)
- ⚠️ GPIO6–11 are used by flash — do NOT use
- ⚠️ ADC2 pins conflict with Wi-Fi when active""",

    'esp8266': """**NodeMCU 1.0 (ESP-12E / ESP8266) Pinout**
- **Power**: VIN (5V), 3V3 (out), GND
- **I2C**: SDA=D2 (GPIO4), SCL=D1 (GPIO5)
- **SPI**: SCK=D5, MISO=D6, MOSI=D7
- **Analog**: A0 (0–3.3V with NodeMCU divider)
- **PWM**: D3, D4, D5, D6
- ⚠️ Single ADC pin, 10-bit, 0–1V raw (NodeMCU adds divider for 3.3V)
- ⚠️ D9/D10 are UART — avoid for GPIO use""",

    'uno': """**Arduino Uno R3 Pinout**
- **Power**: VIN, 5V, 3.3V, GND
- **I2C**: SDA=A4, SCL=A5
- **SPI**: SCK=13, MISO=12, MOSI=11, SS=10
- **UART**: RX=0, TX=1
- **Analog**: A0–A5 (10-bit, 0–5V)
- **PWM**: ~3, ~5, ~6, ~9, ~10, ~11
- ⚠️ 5V logic — use level shifter with 3.3V sensors""",

    'picow': """**Raspberry Pi Pico W (RP2040) Pinout**
- **Power**: VSYS (5V), 3V3 (out), GND
- **I2C**: SDA=GP4, SCL=GP5 (default)
- **SPI**: SCK=GP18, MISO=GP16, MOSI=GP19
- **UART**: TX=GP0, RX=GP1
- **Analog**: GP26, GP27, GP28 (12-bit, 0–3.3V)
- **PWM**: All GPIO except GP23, GP24, GP25
- Built-in Wi-Fi via CYW43439""",

    'mega': """**Arduino Mega 2560 Pinout**
- **Power**: VIN, 5V, 3.3V, GND
- **I2C**: SDA=20, SCL=21
- **SPI**: MOSI=51, MISO=50, SCK=52, SS=53
- **UART**: Serial0 (0,1), Serial1 (18,19), Serial2 (16,17), Serial3 (14,15)
- **PWM**: ~2–~13, ~44–~46 (15 channels)
- **Analog**: A0–A15 (10-bit, 0–5V)""",
}

_WIRING = {
    ('bme280', 'esp32'): """**BME280 → ESP32 Wiring**
| BME280 | ESP32 | Notes |
|--------|-------|-------|
| VCC | 3V3 | ⚠️ 3.3V only |
| GND | GND | Common ground |
| SDA | GPIO21 | I2C data |
| SCL | GPIO22 | I2C clock |
Default I2C address: **0x76** (SDO→GND) or **0x77** (SDO→3V3)
Library: `Adafruit BME280`""",

    ('dht22', 'esp32'): """**DHT22 → ESP32 Wiring**
| DHT22 | ESP32 | Notes |
|-------|-------|-------|
| VCC | 3V3 | |
| DATA | GPIO4 | 4.7kΩ pull-up to 3V3 required |
| GND | GND | |
Library: `DHT sensor library by Adafruit`""",

    ('hcsr04', 'esp32'): """**HC-SR04 Ultrasonic → ESP32 Wiring**
| HC-SR04 | ESP32 | Notes |
|---------|-------|-------|
| VCC | 5V (VIN) | Needs 5V |
| TRIG | GPIO5 | Digital out from ESP32 |
| ECHO | GPIO18 via divider | ⚠️ ECHO is 5V — use voltage divider (1kΩ + 2kΩ) or level shifter |
| GND | GND | |""",

    ('oled_ssd1306', 'esp32'): """**SSD1306 OLED → ESP32 Wiring**
| OLED | ESP32 | Notes |
|------|-------|-------|
| VCC | 3V3 | |
| GND | GND | |
| SDA | GPIO21 | |
| SCL | GPIO22 | |
I2C address: **0x3C** (common) or **0x3D**
Library: `Adafruit SSD1306` + `Adafruit GFX`""",

    ('mpu6050', 'esp32'): """**MPU-6050 IMU → ESP32 Wiring**
| MPU6050 | ESP32 | Notes |
|---------|-------|-------|
| VCC | 3V3 | |
| GND | GND | |
| SDA | GPIO21 | |
| SCL | GPIO22 | |
| INT | GPIO4 | Optional interrupt |
I2C address: **0x68** (AD0→GND) or **0x69** (AD0→3V3)""",
}

_CODE_SNIPPETS = {
    'bme280': '''```cpp
// BME280 Temperature, Humidity, Pressure
#include <Wire.h>
#include <Adafruit_BME280.h>

Adafruit_BME280 bme;

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22); // SDA, SCL for ESP32
  if (!bme.begin(0x76)) {
    Serial.println("BME280 not found! Check wiring.");
    while (1);
  }
}

void loop() {
  Serial.printf("Temp: %.2f°C  Humidity: %.2f%%  Pressure: %.2f hPa\\n",
    bme.readTemperature(), bme.readHumidity(), bme.readPressure() / 100.0F);
  delay(2000);
}
```
**Install**: Adafruit BME280 Library + Adafruit Unified Sensor (Library Manager)''',

    'dht22': '''```cpp
// DHT22 Temperature & Humidity
#include <DHT.h>

#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();
}

void loop() {
  float h = dht.readHumidity();
  float t = dht.readTemperature();
  if (isnan(h) || isnan(t)) {
    Serial.println("DHT read failed! Check wiring and pull-up.");
    delay(2000); return;
  }
  Serial.printf("Temp: %.1f°C  Humidity: %.1f%%\\n", t, h);
  delay(2000);
}
```
**Install**: DHT sensor library by Adafruit''',

    'hcsr04': '''```cpp
// HC-SR04 Ultrasonic Distance Sensor
const int TRIG = 5, ECHO = 18;

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
}

void loop() {
  digitalWrite(TRIG, LOW); delayMicroseconds(2);
  digitalWrite(TRIG, HIGH); delayMicroseconds(10);
  digitalWrite(TRIG, LOW);
  long duration = pulseIn(ECHO, HIGH, 30000); // 30ms timeout
  float distance_cm = duration * 0.034 / 2.0;
  Serial.printf("Distance: %.1f cm\\n", distance_cm);
  delay(500);
}
```
⚠️ ECHO pin outputs 5V — use resistor divider or level shifter before ESP32''',

    'oled': '''```cpp
// SSD1306 OLED Display (I2C)
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

Adafruit_SSD1306 display(128, 64, &Wire, -1);

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED not found!"); while(1);
  }
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);
  display.println("NEXUS IoT");
  display.display();
}

void loop() { /* your code */ }
```
**Install**: Adafruit SSD1306 + Adafruit GFX Library''',

    'wifi': '''```cpp
// ESP32 Wi-Fi Connection
#include <WiFi.h>

const char* ssid = "YOUR_SSID";
const char* password = "YOUR_PASSWORD";

void setup() {
  Serial.begin(115200);
  WiFi.begin(ssid, password);
  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.println("\\nConnected! IP: " + WiFi.localIP().toString());
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
  }
}
```''',

    'mqtt': '''```cpp
// MQTT with PubSubClient (ESP32)
#include <WiFi.h>
#include <PubSubClient.h>

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

void callback(char* topic, byte* payload, unsigned int length) {
  String msg = "";
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];
  Serial.println("MQTT [" + String(topic) + "]: " + msg);
}

void setup() {
  // Connect WiFi first...
  mqtt.setServer("broker.hivemq.com", 1883);
  mqtt.setCallback(callback);
}

void loop() {
  if (!mqtt.connected()) {
    mqtt.connect("nexus_device");
    mqtt.subscribe("nexus/control");
  }
  mqtt.loop();
  mqtt.publish("nexus/sensor", "hello");
  delay(5000);
}
```
**Install**: PubSubClient by Nick O'Leary''',
}

_CONCEPTS = {
    'i2c': """**I2C Protocol**
- 2-wire serial: SDA (data) + SCL (clock)
- Supports multiple devices on same bus (each has a unique 7-bit address)
- Speed: Standard 100kHz, Fast 400kHz
- Pull-up resistors required (typically 4.7kΩ to 3.3V)
- Max cable length: ~1m at 100kHz
- Common addresses: 0x3C (SSD1306), 0x68 (MPU6050), 0x76 (BME280)
- Scan all devices with the I2C scanner sketch""",

    'spi': """**SPI Protocol**
- 4-wire: MOSI, MISO, SCK, CS (chip select)
- Full duplex, faster than I2C (up to 80MHz on ESP32)
- Each device needs its own CS line
- No pull-up resistors needed
- Common uses: displays, SD cards, LoRa, nRF24L01""",

    'uart': """**UART / Serial Protocol**
- 2-wire: TX → RX, RX ← TX (crossed connections)
- Common baud rates: 9600, 115200
- Used by: GPS modules, GSM/SIM modules, Bluetooth HC-05
- ESP32 has 3 hardware UARTs (Serial0/1/2)
- ⚠️ Cross TX→RX, RX←TX when connecting two devices""",

    'pwm': """**PWM (Pulse Width Modulation)**
- Varies duty cycle (0–100%) to control power/speed
- LED dimming: analogWrite(pin, 0–255) on Arduino
- ESP32: ledcSetup(ch, freq, bits) + ledcWrite(ch, duty)
- Servo control: 50Hz, 1ms pulse = 0°, 2ms pulse = 180°
- Motor speed: use H-bridge + PWM for direction + speed""",

    'adc': """**ADC (Analog-to-Digital Converter)**
- Converts voltage to digital value
- ESP32: 12-bit (0–4095) on ADC1, 3.3V max
- Arduino Uno: 10-bit (0–1023) on A0–A5, 5V max
- ⚠️ ESP32 ADC2 disabled when Wi-Fi is active — use ADC1 pins (GPIO32–39)
- ⚠️ ESP32 ADC is non-linear near 0V and 3.3V — use voltage divider for accuracy""",
}

_FAQ = {
    'power': """**ESP32 Power Options**
1. **USB**: 5V via USB-UART chip → onboard 3.3V regulator
2. **VIN pin**: 5V → onboard regulator (not suitable for high current)
3. **3V3 pin**: Direct 3.3V regulated input (bypass onboard regulator)
4. **Battery**: LiPo (3.7V) via TP4056 charger + protection circuit
- GPIO max current: 12mA per pin, 40mA total
- Never power motors from GPIO — use a separate supply + transistor""",

    'upload': """**ESP32 Upload Troubleshooting**
1. Install CP210x or CH340 USB-UART driver
2. Hold BOOT button while clicking Upload, release after "Connecting..."
3. Board: "ESP32 Dev Module" in Arduino IDE
4. Baud: 115200
5. If still failing: add 10µF capacitor between EN and GND
6. Check that no other code is using Serial (conflicts with upload)""",

    'voltage': """**Voltage Level Compatibility**
- ESP32: 3.3V logic only — DO NOT connect 5V signals directly to GPIO
- Arduino Uno: 5V logic — 3.3V sensors need level shifter
- HC-SR04 ECHO: 5V → use 1kΩ + 2kΩ voltage divider
- Level shifter: bidirectional (e.g. BSS138-based) for I2C/SPI
- Logic level converter modules available for 2–4 channels""",
}


# --------------------------------------------------------------------------- #
# Query matcher                                                                #
# --------------------------------------------------------------------------- #

def _match(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k in t for k in keywords)


def answer(prompt: str) -> str:
    """Return a curated engineering answer or a helpful suggestion."""
    p = prompt.strip()
    pl = p.lower()

    # Board pinouts
    for board, kb in _PINOUTS.items():
        if board in pl and _match(pl, ['pin', 'pinout', 'gpio', 'connect', 'sda', 'scl', 'io', 'i/o', 'analog', 'digital']):
            return kb + "\n\n*— NEXUS Knowledge Base (no API key required)*"

    # Wiring help
    for (sensor, board), kb in _WIRING.items():
        if sensor.replace('_', '') in pl.replace(' ', '').replace('_', '') or sensor.split('_')[0] in pl:
            if board in pl or 'esp32' in pl or board not in pl:
                return kb + "\n\n*— NEXUS Knowledge Base (no API key required)*"

    # Code snippets
    for part, code in _CODE_SNIPPETS.items():
        if _match(pl, [part, part.replace('_', ' ')]) and _match(pl, ['code', 'sketch', 'program', 'example', 'how', 'write', 'arduino', 'firmware']):
            return f"**{part.upper()} Arduino Code Example**\n\n{code}\n\n*— NEXUS Knowledge Base (no API key required)*"

    # Protocol concepts
    for concept, kb in _CONCEPTS.items():
        if concept in pl and _match(pl, ['what', 'how', 'explain', 'protocol', 'work', 'use', 'differ']):
            return kb + "\n\n*— NEXUS Knowledge Base (no API key required)*"

    # FAQ topics
    if _match(pl, ['power', 'battery', 'vin', 'supply', 'volt', '3v3', '5v', 'lipo']):
        return _FAQ['power'] + "\n\n*— NEXUS Knowledge Base (no API key required)*"
    if _match(pl, ['upload', 'flash', 'boot', 'driver', 'cp210', 'ch340', 'connect']):
        return _FAQ['upload'] + "\n\n*— NEXUS Knowledge Base (no API key required)*"
    if _match(pl, ['5v', '3.3v', 'level', 'shifter', 'logic', 'voltage', 'tolerant', 'compatible']):
        return _FAQ['voltage'] + "\n\n*— NEXUS Knowledge Base (no API key required)*"

    # Pinout fallback for any board name
    for board, kb in _PINOUTS.items():
        if board in pl:
            return kb + "\n\n*— NEXUS Knowledge Base (no API key required)*"

    # Generic help
    topics = ', '.join(f'`{k}`' for k in list(_PINOUTS) + list(_CODE_SNIPPETS) + list(_CONCEPTS))
    return (
        f"**NEXUS Engineering Assistant** *(offline knowledge base)*\n\n"
        f"I can answer questions about IoT hardware and programming. "
        f"Try asking about:\n"
        f"- Board pinouts: esp32, esp8266, uno, picow\n"
        f"- Wiring: 'how to connect bme280 to esp32'\n"
        f"- Code examples: 'show me dht22 code'\n"
        f"- Protocols: i2c, spi, uart, pwm, adc\n"
        f"- Topics: power, voltage, upload\n\n"
        f"*To enable full AI chat (GPT/Gemini), configure an API key in Admin > AI Providers.*\n\n"
        f"*— NEXUS Knowledge Base (no API key required)*"
    )


def stream_answer(prompt: str) -> Iterator[str]:
    """Yield the answer in ~100-char chunks to simulate streaming."""
    text = answer(prompt)
    chunk_size = 80
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]
