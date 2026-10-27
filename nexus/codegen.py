"""Generate project firmware from the same catalog used for BOM and wiring.

Output status is always explicit: seeded firmware is statically reviewed, not
hardware-tested.  Secrets are placeholders.  Pin defines come from the same
assignment used by the wiring table so the three artefacts cannot diverge.
"""
from __future__ import annotations

import re
from typing import Any

from . import hardware

PLACEHOLDER_NOTE = "Replace ALL YOUR_* placeholders before deploying. Never commit real credentials."

PLATFORM_DEFS = {
    "esp32": ("WiFi.h", "PubSubClient.h", "HTTPClient.h"),
    "esp32s3": ("WiFi.h", "PubSubClient.h", "HTTPClient.h"),
    "esp32cam": ("WiFi.h", "PubSubClient.h", "HTTPClient.h"),
    "esp8266": ("ESP8266WiFi.h", "PubSubClient.h", "ESP8266HTTPClient.h"),
    "uno": (),
    "picow": ("WiFi.h", "PubSubClient.h", "HTTPClient.h"),
}

ADC_CONFIG = {
    "esp32": (4095.0, 3.3),
    "esp32s3": (4095.0, 3.3),
    "esp32cam": (4095.0, 3.3),
    "esp8266": (1023.0, 3.3),
    "uno": (1023.0, 5.0),
    "picow": (4095.0, 3.3),
    "rpi4": (4095.0, 3.3),
}

COMMS: dict[str, dict[str, Any]] = {
    "serial": {
        "label": "USB serial (115200 baud)",
        "includes": [], "globals": [], "setup": [],
        "publish": ["Serial.print(F(\"[DATA] \")); Serial.println(payload);"],
        "config": [], "docs": "https://www.arduino.cc/reference/en/language/functions/communication/serial/",
    },
    "wifi_mqtt": {
        "label": "Wi-Fi + MQTT (TLS-ready broker)",
        "includes": ["PubSubClient.h"],
        "globals": [
            "const char* WIFI_SSID = \"YOUR_WIFI_SSID\";",
            "const char* WIFI_PASSWORD = \"YOUR_WIFI_PASSWORD\";",
            "const char* MQTT_HOST = \"YOUR_MQTT_BROKER_HOST\";",
            "const uint16_t MQTT_PORT = 1883;",
            "const char* MQTT_USER = \"YOUR_MQTT_USER\";",
            "const char* MQTT_PASS = \"YOUR_MQTT_PASSWORD\";",
            "WiFiClient netClient;",
            "PubSubClient mqtt(netClient);",
            "uint32_t lastReconnectAttempt = 0;",
        ],
        "setup": ["WiFi.mode(WIFI_STA);", "mqtt.setServer(MQTT_HOST, MQTT_PORT);",
                  "mqtt.setBufferSize(512);"],
        "publish": [
            "// --- Non-blocking Wi-Fi / MQTT reconnection ---",
            "if (WiFi.status() != WL_CONNECTED) {",
            "  static uint32_t wifiAt = 0;",
            "  if (millis() - wifiAt > 5000) { wifiAt = millis();",
            "    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);",
            "    Serial.println(F(\"[WARN] Wi-Fi reconnecting...\")); }",
            "} else if (!mqtt.connected()) {",
            "  if (millis() - lastReconnectAttempt > 5000) {",
            "    lastReconnectAttempt = millis();",
            "    if (mqtt.connect(\"nexus-client-YOUR_DEVICE_ID\", MQTT_USER, MQTT_PASS)) {",
            "      Serial.println(F(\"[INFO] MQTT connected\"));",
            "      mqtt.subscribe(\"nexus/YOUR_DEVICE_ID/cmd\");",
            "    } else { Serial.print(F(\"[ERR] MQTT rc=\")); Serial.println(mqtt.state()); }",
            "  }",
            "} else {",
            "  mqtt.loop();",
            "  char topic[96]; snprintf(topic, sizeof(topic), \"nexus/%s/telemetry\", \"YOUR_DEVICE_ID\");",
            "  if (!mqtt.publish(topic, payload.c_str(), false)) { Serial.println(F(\"[ERR] MQTT publish failed\")); }",
            "  else { Serial.print(F(\"[TX] \")); Serial.println(payload); }",
            "}",
        ],
        "config": ["YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD", "YOUR_MQTT_BROKER_HOST",
                   "YOUR_MQTT_USER", "YOUR_MQTT_PASSWORD", "YOUR_DEVICE_ID"],
        "docs": "https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html",
    },
    "wifi_http": {
        "label": "Wi-Fi + HTTPS REST POST",
        "includes": ["HTTPClient.h"],
        "globals": [
            "const char* WIFI_SSID = \"YOUR_WIFI_SSID\";",
            "const char* WIFI_PASSWORD = \"YOUR_WIFI_PASSWORD\";",
            "const char* API_ENDPOINT = \"https://YOUR_API_HOST/telemetry\";",
            "const char* API_TOKEN = \"YOUR_API_TOKEN\";",
        ],
        "setup": ["WiFi.mode(WIFI_STA);", "WiFi.begin(WIFI_SSID, WIFI_PASSWORD);",
                  "uint32_t wifiStart = millis();",
                  "while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 15000) { delay(250); }",
                  "Serial.println(WiFi.status() == WL_CONNECTED ? F(\"[INFO] Wi-Fi up\") : F(\"[ERR] Wi-Fi failed\"));"],
        "publish": [
            "if (WiFi.status() == WL_CONNECTED) {",
            "  HTTPClient http; http.begin(API_ENDPOINT);",
            "  http.addHeader(\"Content-Type\", \"application/json\");",
            "  http.addHeader(\"Authorization\", String(\"Bearer \") + API_TOKEN);",
            "  http.setTimeout(5000);",
            "  int code = http.POST(payload);",
            "  if (code < 200 || code >= 300) { Serial.print(F(\"[ERR] HTTP \")); Serial.println(code); }",
            "  else { Serial.print(F(\"[TX] \")); Serial.println(payload); }",
            "  http.end();",
            "} else { Serial.println(F(\"[WARN] Wi-Fi down; buffering locally\")); }",
        ],
        "config": ["YOUR_WIFI_SSID", "YOUR_WIFI_PASSWORD", "YOUR_API_HOST", "YOUR_API_TOKEN"],
        "docs": "https://docs.espressif.com/projects/arduino-esp32/en/latest/api/http.html",
    },
    "espnow": {
        "label": "ESP-NOW peer-to-peer (no router)",
        "includes": ["esp_now.h", "WiFi.h"],
        "globals": ["uint8_t peerMac[] = {0xAA,0xBB,0xCC,0xDD,0xEE,0xFF};  // YOUR_PEER_MAC",
                    "esp_now_peer_info_t peer;"],
        "setup": ["WiFi.mode(WIFI_STA);",
                  "if (esp_now_init() != ESP_OK) { Serial.println(F(\"[ERR] ESP-NOW init failed\")); }",
                  "memcpy(peer.peer_addr, peerMac, 6); peer.channel = 1; peer.encrypt = false;",
                  "esp_now_add_peer(&peer);"],
        "publish": ["esp_err_t r = esp_now_send(peerMac, (uint8_t*)payload.c_str(), payload.length());",
                    "Serial.println(r == ESP_OK ? F(\"[TX] ESP-NOW OK\") : F(\"[ERR] ESP-NOW send failed\"));"],
        "config": ["YOUR_PEER_MAC"],
        "docs": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html",
    },
    "ble": {
        "label": "Bluetooth Low Energy notifications",
        "includes": ["BLEDevice.h", "BLEServer.h", "BLEUtils.h", "BLE2902.h"],
        "globals": ["BLECharacteristic* telemetryChar = nullptr;", "bool deviceConnected = false;"],
        "setup": ["BLEDevice::init(\"NEXUS-YOUR_DEVICE_ID\");",
                  "BLEServer* server = BLEDevice::createServer();",
                  "BLEService* svc = server->createService(\"180F\");",
                  "telemetryChar = svc->createCharacteristic(\"2A19\", BLECharacteristic::PROPERTY_NOTIFY);",
                  "telemetryChar->addDescriptor(new BLE2902()); svc->start(); server->getAdvertising()->start();"],
        "publish": ["if (telemetryChar) { telemetryChar->setValue(payload); telemetryChar->notify();",
                    "  Serial.print(F(\"[BLE TX] \")); Serial.println(payload); }"],
        "config": ["YOUR_DEVICE_ID"],
        "docs": "https://docs.espressif.com/projects/arduino-esp32/en/latest/api/ble.html",
    },
    "lora": {
        "label": "LoRa / LoRaWAN-ready radio link",
        "includes": [], "globals": [], "setup": [],
        "publish": ["// LoRa transmission is performed by the SX1278 driver section above."],
        "config": ["YOUR_REGIONAL_ISM_FREQUENCY"],
        "docs": "https://www.semtech.com/products/wireless-rf/lora-connect/sx1276",
    },
    "gsm": {
        "label": "Cellular MQTT/HTTP via GSM modem",
        "includes": ["TinyGsmClient.h"], "globals": [],
        "setup": ["// modem network registration is performed by the modem section above."],
        "publish": ["if (modem.isNetworkConnected()) { TinyGsmClient client(modem); client.connect(\"YOUR_API_HOST\", 80);",
                    "  client.print(String(\"POST /telemetry HTTP/1.1\\r\\nHost: YOUR_API_HOST\\r\\n\") +",
                    "    String(\"Content-Type: application/json\\r\\nContent-Length: \") + payload.length() +",
                    "    String(\"\\r\\nConnection: close\\r\\n\\r\\n\") + payload);",
                    "  client.stop(); Serial.print(F(\"[TX] \")); Serial.println(payload);",
                    "} else { Serial.println(F(\"[ERR] No cellular network; buffering locally\")); }"],
        "config": ["YOUR_API_HOST", "YOUR_APN"],
        "docs": "https://tinygs.com/",
    },
    "rs485": {
        "label": "RS-485 / Modbus RTU fieldbus",
        "includes": [], "globals": [], "setup": [],
        "publish": ["Serial.print(F(\"[MODBUS] \")); Serial.println(payload);"],
        "config": ["YOUR_MODBUS_SLAVE_ID"],
        "docs": "https://www.analog.com/en/products/max485.html",
    },
    "ethernet": {
        "label": "Wired Ethernet (W5500)",
        "includes": ["Ethernet.h"], "globals": [], "setup": [],
        "publish": ["Serial.print(F(\"[ETH] \")); Serial.println(payload);"],
        "config": ["YOUR_STATIC_IP"], "docs": "https://www.wiznet.io/product-item/w5500/",
    },
    "sd_local": {
        "label": "Local SD-card / serial data logger (offline)",
        "includes": [], "globals": [], "setup": [],
        "publish": ["Serial.print(F(\"[LOG] \")); Serial.println(payload);",
                    "// SD write is performed by the storage driver section above."],
        "config": [], "docs": "https://www.arduino.cc/reference/en/libraries/sd/",
    },
}

TOKEN_RE = re.compile(r"@([A-Z0-9_]+)@")


def _tokens(part: dict, roles: dict, b: dict) -> dict:
    t = {k.upper(): str(v) for k, v in roles.items()}
    buses = {}
    buses.update({k.upper(): str(v) for k, v in b["i2c"].items()})
    buses.update({k.upper(): str(v) for k, v in b["spi"].items()})
    buses.update({k.upper(): str(v) for k, v in b["uart"].items()})
    for k, v in buses.items():
        t.setdefault(k, v)
    t.setdefault("CS", str(b["cs_pool"][0]))
    t.setdefault("RST", str(b["digital_pool"][-1]))
    t.setdefault("DIO0", str(b["digital_pool"][-2]))
    t.setdefault("CE", str(b["digital_pool"][-3]))
    t.setdefault("DE", str(b["digital_pool"][-4]))
    t.setdefault("DT", str(b["digital_pool"][-1]))
    first = next((str(v) for v in roles.values() if str(v).isdigit() or str(v).startswith(("A", "D"))), "2")
    t.setdefault("PIN", first)
    t.setdefault("TRIG", t.get("TRIG", first))
    t.setdefault("ECHO", t.get("ECHO", first))
    return t


def _apply(text: str, tokens: dict) -> str:
    def sub(m):
        return tokens.get(m.group(1), m.group(0))
    return TOKEN_RE.sub(sub, text)


def _config_block(board_key: str) -> str:
    adc_max, vref = ADC_CONFIG.get(board_key, (4095.0, 3.3))
    return f"""// ---- Board constants and CALIBRATION PLACEHOLDERS -----------------------
// {PLACEHOLDER_NOTE}
#define ADC_MAX {adc_max:.1f}F
#define VREF {vref:.2f}F
#define DRY_RAW  {adc_max*0.75:.0f}F   // TODO: measure in dry air for THIS sensor
#define WET_RAW  {adc_max*0.35:.0f}F   // TODO: measure in water for THIS sensor
#define EMPTY_RAW {adc_max*0.10:.0f}F  // TODO: measure with empty tank
#define FULL_RAW {adc_max*0.90:.0f}F   // TODO: measure with full tank
#define CAL_FACTOR 420.0F              // TODO: derive from a known calibration mass
#define ACS_SENSITIVITY 0.185F         // TODO: ACS712-05B; verify the part marking
#define LOAD_VOLTAGE 12.0F             // TODO: actual DC load voltage
#define TEMP_OFFSET 0.0F               // TODO: measured sensor offset in deg C
#define MOUNT_HEIGHT_CM 200.0F         // TODO: surveyed sensor-to-datum height
#define ANEMO_FACTOR 1.0F              // TODO: calibrate against a reference anemometer
#define BATTERY_AH 7.0F                // TODO: measured battery capacity
#define TANK_AREA_CM2 1200.0F          // TODO: real tank cross-section
#define TANK_HEIGHT_CM 150.0F          // TODO: real tank height
#define BIN_HEIGHT_CM 60.0F            // TODO: measured lid-to-floor height
#define FUEL_TANK_HEIGHT_CM 60.0F      // TODO: measured fuel tank height
#define FUEL_TANK_AREA_CM2 1500.0F     // TODO: measured tank cross-section
#define CRED_EXPIRY_EPOCH 1767225600UL // TODO: real credential expiry (Unix epoch)
#define SAMPLE_INTERVAL_MS 5000UL
static uint32_t rtcEpochPlaceholder = 1735689600UL;  // TODO: convert RTC DateTime to epoch
static uint32_t bootCounterPlaceholder = 0;          // TODO: persist boot count in NVS

float fmap(float x, float in_min, float in_max, float out_min, float out_max) {{
  if (fabsf(in_max - in_min) < 0.0001F) return out_min;
  float v = (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
  if (out_min < out_max) return constrain(v, out_min, out_max);
  return constrain(v, out_max, out_min);
}}"""


PART_HEADERS = {
    "dht22": ["DHT.h", "Adafruit_Sensor.h"],
    "dht11": ["DHT.h", "Adafruit_Sensor.h"],
    "bme280": ["Adafruit_BME280.h", "Adafruit_Sensor.h"],
    "bme680": ["Adafruit_BME680.h", "Adafruit_Sensor.h"],
    "sht31": ["Adafruit_SHT31.h"],
    "ds18b20": ["OneWire.h", "DallasTemperature.h"],
    "bh1750": ["BH1750.h"],
    "vl53l0x": ["VL53L0X.h"],
    "pms5003": ["Adafruit_PM25AQI.h"],
    "sds011": ["SDS011.h"],
    "ccs811": ["Adafruit_CCS811.h"],
    "scd30": ["Adafruit_SCD30.h"],
    "ina219": ["Adafruit_INA219.h"],
    "pzem": ["PZEM004Tv30.h"],
    "hx711": ["HX711.h"],
    "mpu6050": ["Adafruit_MPU6050.h", "Adafruit_Sensor.h"],
    "max30102": ["MAX30105.h"],
    "mlx90614": ["Adafruit_MLX90614.h"],
    "gps": ["TinyGPS++.h"],
    "rfid": ["MFRC522.h"],
    "rtc": ["RTClib.h"],
    "sdcard": ["SD.h", "SPI.h"],
    "ws2812b": ["Adafruit_NeoPixel.h"],
    "servo": ["Servo.h"],  # overridden per board below
    "oled": ["Adafruit_GFX.h", "Adafruit_SSD1306.h"],
    "lcd": ["LiquidCrystal_I2C.h"],
    "eink": ["GxEPD2_BW.h"],
    "lora": ["LoRa.h", "SPI.h"],
    "nrf24": ["RF24.h", "SPI.h"],
    "gsm": ["TinyGsmClient.h"],
    "rs485": ["ModbusMaster.h"],
    "ethernet": ["Ethernet.h", "SPI.h"],
    "canbus": ["mcp_can.h", "SPI.h"],
    "camera": ["esp_camera.h"],
    "mic_i2s": ["driver/i2s.h"],
}


def generate_arduino(spec: dict, parts: list[str], pins: dict, comms: str) -> dict:
    b = hardware.BOARDS[spec["board"]]
    comm = COMMS.get(comms, COMMS["serial"])
    includes = ["Arduino.h", "Wire.h", "SPI.h", "math.h"] + list(comm["includes"])
    for key in parts:
        if key in hardware.PARTS:
            for lib in hardware.PARTS[key]["libs"]:
                # libs entries are human-readable descriptions; only add real headers
                m = re.search(r"<([A-Za-z0-9_]+\.h)>", lib)
                if m and m.group(1) not in includes:
                    includes.append(m.group(1))
    libraries = sorted({lib for key in parts if key in hardware.PARTS
                        for lib in hardware.PARTS[key]["libs"]})
    if comms.startswith("wifi"):
        libraries = ["PubSubClient by Nick O'Leary (2.8.x)"] + libraries

    lines: list[str] = []
    lines.append("/* =====================================================================")
    lines.append(f"   NEXUS IoT - {spec['title']}")
    lines.append(f"   Board: {b['name']}")
    lines.append(f"   Communication: {comm['label']}")
    lines.append("   Code status: STATICALLY REVIEWED - NOT hardware-tested. Bench-verify")
    lines.append("   every pin, voltage and library version before applying power.")
    lines.append(f"   {PLACEHOLDER_NOTE}")
    lines.append("   ===================================================================== */")
    # Real library headers for every catalog part. Library metadata in the
    # catalog is human-readable, so the headers are mapped explicitly here.
    if "gsm" in parts:
        lines.append("#define TINY_GSM_MODEM_SIM800   // select the modem model BEFORE including TinyGSM")
    extra_headers = []
    for key in parts:
        headers = PART_HEADERS.get(key, [])
        if key == "servo":
            headers = ["ESP32Servo.h"] if spec["board"] in ("esp32", "esp32s3", "esp32cam") else ["Servo.h"]
        extra_headers.extend(headers)
    for inc in dict.fromkeys(includes + extra_headers):
        lines.append(f"#include <{inc}>")
    lines.append("")
    lines.append("")
    lines.append(_config_block(spec["board"]))
    logic_text = spec.get("logic", "")
    pwm_pin = None
    if "ledcWrite" in logic_text or "analogWrite" in logic_text:
        for key in parts:
            pp = hardware.PARTS.get(key, {})
            if pp.get("group") == "Actuator" and pins.get(key):
                pwm_pin = next((v for v in pins[key].values() if str(v).isdigit()), None)
                if pwm_pin:
                    break
        esp32_family = spec["board"] in ("esp32", "esp32s3", "esp32cam")
        if pwm_pin and esp32_family:
            lines.append("// PWM channel for the actuator control loop")
            lines.append("#define analogWrite(pin, val) ledcWrite(0, val)  // ESP32 PWM shim")
            lines.append(f"#define NEXUS_PWM_PIN {pwm_pin}")
    lines.append("")
    lines.append("// ---- Communication configuration ----")
    board_tokens = _tokens({}, {}, b)
    for g in comm["globals"]:
        lines.append(_apply(g, board_tokens))
    lines.append("")
    lines.append("// ---- Sensor / actuator driver objects and pin definitions ----")
    for key in parts:
        p = hardware.PARTS.get(key)
        if not p or p["iface"] in ("passive", "power"):
            continue
        tok = _tokens(p, pins.get(key, {}), b)
        if p["globs"]:
            lines.append(f"// {p['name']}")
            for g in p["globs"]:
                # Headers are emitted once at the top (with board-specific choices).
                if g.startswith("#include ") or g.startswith("#define TINY_GSM_MODEM_"):
                    continue
                lines.append(_apply(g, tok))
    lines.append("")
    lines.append("String payload = \"\";")
    lines.append("String displayLine = \"\";")
    lines.append("String logLine = \"\";")
    lines.append("unsigned long lastSample = 0;")
    lines.append("")
    lines.append("void setup() {")
    lines.append("  Serial.begin(115200);")
    lines.append("  delay(200);")
    lines.append(f"  Serial.println(F(\"[BOOT] {spec['slug']} on {b['name']}\"));")
    i2c_added = spi_added = False
    for key in parts:
        p = hardware.PARTS.get(key)
        if not p:
            continue
        tok = _tokens(p, pins.get(key, {}), b)
        if p["iface"] == "i2c" and not i2c_added:
            lines.append(f"  Wire.begin({b['i2c']['SDA']}, {b['i2c']['SCL']});")
            i2c_added = True
        if p["iface"] == "spi" and not spi_added:
            lines.append(f"  SPI.begin({b['spi']['SCK']}, {b['spi']['MISO']}, {b['spi']['MOSI']}, {b['cs_pool'][0]});")
            spi_added = True
        for s in p["setup"]:
            lines.append("  " + _apply(s, tok))
    if pwm_pin and spec["board"] in ("esp32", "esp32s3", "esp32cam"):
        lines.append("  // Arduino-ESP32 2.x PWM API; for core 3.x use ledcAttach(NEXUS_PWM_PIN, 5000, 8);")
        lines.append("  ledcSetup(0, 5000, 8);")
        lines.append("  ledcAttachPin(NEXUS_PWM_PIN, 0);")
    for s in comm["setup"]:
        lines.append("  " + s)
    lines.append("  Serial.println(F(\"[INFO] setup complete\"));")
    lines.append("}")
    lines.append("")
    lines.append("void loop() {")
    lines.append("  if (millis() - lastSample < SAMPLE_INTERVAL_MS) { delay(20); return; }")
    lines.append("  lastSample = millis();")
    lines.append("  payload = \"\"; displayLine = \"\"; logLine = \"\";")
    lines.append("")
    output_groups = {"Comms", "Display", "Storage"}
    lines.append("  // ---- Sensor reads (driver-level error checks included) ----")
    for key in parts:
        p = hardware.PARTS.get(key)
        if not p or p["iface"] in ("passive", "power") or not p["read"] or p["group"] in output_groups:
            continue
        tok = _tokens(p, pins.get(key, {}), b)
        lines.append(f"  // {p['name']}")
        raw_var = "raw_" + re.sub(r"[^a-zA-Z0-9_]", "_", key)
        for r in p["read"]:
            # Every part gets its own raw-ADC variable so multi-sensor builds
            # never redeclare `int raw` inside loop().
            line = re.sub(r"\braw\b", raw_var, _apply(r, tok))
            lines.append("  " + line)
        lines.append("")
    lines.append("  // ---- Project-specific processing ----")
    for l in spec.get("logic", "").strip().splitlines():
        lines.append("  " + l)
    lines.append("")
    lines.append("  if (payload.length() == 0) {")
    lines.append("    char fallbackBuf[256]; snprintf(fallbackBuf, sizeof(fallbackBuf), \"{\\\"device\\\":\\\"YOUR_DEVICE_ID\\\",\\\"ts\\\":%lu,\\\"project\\\":\\\"%s\\\"}\",")
    lines.append(f"                             (unsigned long)millis(), \"{spec['slug']}\");")
    lines.append("    payload = String(fallbackBuf);")
    lines.append("  }")
    lines.append("  logLine = payload;")
    lines.append("")
    lines.append("  // ---- Displays, local storage and radio transports (need the payload) ----")
    for key in parts:
        p = hardware.PARTS.get(key)
        if not p or p["group"] not in output_groups or not p["read"]:
            continue
        tok = _tokens(p, pins.get(key, {}), b)
        lines.append(f"  // {p['name']}")
        for r in p["read"]:
            lines.append("  " + _apply(r, tok))
        lines.append("")
    lines.append("  // ---- Communication / reconnection behaviour ----")
    for line in comm["publish"]:
        lines.append("  " + line)
    lines.append("}")
    code = "\n".join(lines) + "\n"
    code = code.replace("map((float)raw", "fmap((float)raw")
    return {
        "language": "Arduino C++",
        "code": code,
        "libraries": libraries,
        "board_core": b["core"],
        "upload_instructions": b["upload"],
        "config_placeholders": comm["config"],
        "expected_output": [
            "[BOOT] " + spec["slug"],
            "[INFO] setup complete",
            "[DATA]/[TX] {\"device\":\"YOUR_DEVICE_ID\", ... }",
        ],
        "sample_log": "[BOOT] " + spec["slug"] + "\n[INFO] setup complete\n[DATA] " +
                     "{\"device\":\"YOUR_DEVICE_ID\",\"ts\":12000,\"project\":\"" + spec["slug"] + "\"}",
        "status": "Statically reviewed - NOT hardware-tested",
        "review_notes": [
            "Pin defines are generated from the project's wiring table.",
            "Library version numbers are the documented API families, not a guarantee of API compatibility; compile before wiring.",
            "Calibration constants are placeholders and must be measured on real hardware.",
            "Secrets are placeholders; use environment-specific provisioning or NVS, never source-code literals, in production.",
        ],
    }


def generate_python(spec: dict, parts: list[str], pins: dict, comms: str) -> dict:
    """Linux host (Raspberry Pi) firmware using documented Python libraries."""
    b = hardware.BOARDS[spec["board"]]
    lines = [
        "#!/usr/bin/env python3",
        f'"""NEXUS IoT - {spec["title"]}\n'
        f"Board: {b['name']}\n"
        "Code status: STATICALLY REVIEWED - NOT hardware-tested.\n"
        f"{PLACEHOLDER_NOTE}\n"
        '"""',
        "import json, os, time, math, logging",
        "from datetime import datetime, timezone",
        "",
        "logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')",
        "LOG = logging.getLogger('nexus')",
        "",
        "SAMPLE_INTERVAL_S = float(os.getenv('SAMPLE_INTERVAL_S', '5'))",
        "DEVICE_ID = os.getenv('DEVICE_ID', 'YOUR_DEVICE_ID')",
        "MQTT_HOST = os.getenv('MQTT_HOST', 'YOUR_MQTT_BROKER_HOST')",
        "MQTT_TOPIC = os.getenv('MQTT_TOPIC', 'nexus/' + DEVICE_ID + '/telemetry')",
        "",
        "# pip install: see libraries[] in the project metadata (paho-mqtt,",
        "# adafruit-circuitpython-..., gpiozero, smbus2 as required).",
    ]
    i2c_parts = [k for k in parts if hardware.PARTS.get(k, {}).get("iface") == "i2c"]
    digital_parts = [k for k in parts if hardware.PARTS.get(k, {}).get("iface") == "digital"]
    if i2c_parts:
        lines += ["import board, busio", "i2c = busio.I2C(board.SCL, board.SDA)"]
        for k in i2c_parts:
            lines.append(f"# TODO initialise driver for {hardware.PARTS[k]['name']} (see {hardware.PARTS[k]['docs']})")
            lines.append(f"{k}_dev = None  # replace with the library driver instance")
    if digital_parts:
        lines += ["from gpiozero import DigitalOutputDevice, DigitalInputDevice"]
    lines += ["", "def read_sensors():", "    data = {}"]
    for k in parts:
        p = hardware.PARTS.get(k)
        if not p or p["iface"] in ("passive", "power", "display", "storage"):
            continue
        lines.append(f"    # {p['name']} - verify driver register mapping before use")
        lines.append(f"    # data['{k}'] = ...  # TODO: library call; see docs")
    lines += [
        "    data.setdefault('note', 'driver stubs must be replaced with the documented library calls')",
        "    return data", "",
        "def publish(payload):",
        "    # Preferred: paho-mqtt with reconnect loop. Falls back to a log line when not installed.",
        "    try:",
        "        import paho.mqtt.client as mqtt",
        "        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=DEVICE_ID)",
        "        client.username_pw_set(os.getenv('MQTT_USER','YOUR_MQTT_USER'), os.getenv('MQTT_PASS','YOUR_MQTT_PASSWORD'))",
        "        client.connect(MQTT_HOST, int(os.getenv('MQTT_PORT','1883')), 60)",
        "        client.loop_start(); client.publish(MQTT_TOPIC, json.dumps(payload), qos=1).wait_for_publish(5)",
        "        client.loop_stop(); client.disconnect()",
        "        LOG.info('[TX] %s', payload)",
        "    except Exception as exc:  # noqa: BLE001",
        "        LOG.warning('[WARN] publish failed (%s); payload buffered locally: %s', exc, payload)",
        "        with open('/tmp/nexus_buffer.jsonl', 'a', encoding='utf-8') as fh:",
        "            fh.write(json.dumps(payload) + '\\n')",
        "",
        "def main():",
        "    LOG.info('[BOOT] " + spec["slug"] + " on " + b["name"] + "')",
        "    while True:",
        "        try:",
        "            data = read_sensors()",
        "            payload = {'device': DEVICE_ID, 'project': '" + spec["slug"] + "',",
        "                       'ts': datetime.now(timezone.utc).isoformat(), 'data': data}",
        "            publish(payload)",
        "        except Exception as exc:  # noqa: BLE001",
        "            LOG.exception('[ERR] sample failed: %s', exc)",
        "        time.sleep(SAMPLE_INTERVAL_S)",
        "",
        "if __name__ == '__main__':",
        "    main()",
    ]
    return {
        "language": "Python 3 (Raspberry Pi OS)",
        "code": "\n".join(lines) + "\n",
        "libraries": ["paho-mqtt (2.x, optional)", "gpiozero (2.x)", "adafruit-circuitpython drivers for the listed I2C parts"],
        "board_core": b["core"],
        "upload_instructions": b["upload"] + " Create a virtualenv, pip install the listed libraries, run as a systemd service.",
        "config_placeholders": ["DEVICE_ID", "MQTT_HOST", "MQTT_USER", "MQTT_PASS"],
        "expected_output": ["[BOOT] " + spec["slug"], "[TX] {'device': ...}"],
        "sample_log": "[BOOT] " + spec["slug"] + "\n[TX] {'device': 'YOUR_DEVICE_ID', 'data': {}}",
        "status": "Statically reviewed scaffold - NOT hardware-tested",
        "review_notes": [
            "Linux hosts need explicit driver initialisation; TODO stubs are intentional and documented.",
            "No GPIO can be assumed pin-compatible with a microcontroller board; BCM numbering is used.",
        ],
    }


def generate_firmware(spec: dict, parts: list[str], pins: dict, comms: str) -> dict:
    if hardware.BOARDS[spec["board"]]["platform"] == "linux_python":
        return generate_python(spec, parts, pins, comms)
    return generate_arduino(spec, parts, pins, comms)
