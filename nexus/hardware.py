"""Hardware knowledge base.

Every part carries its real electrical interface, logic level, current budget,
documentation link, Arduino driver snippets and calibration notes.  The same
records feed the BOM, wiring table, architecture diagrams, generated firmware
and the circuit validation rules -- which keeps them mutually consistent.

Pin tokens in templates: @PIN@ (single GPIO), @SDA@/@SCL@, @SCK@/@MISO@/@MOSI@/@CS@,
@RX@/@TX@, @A@ (analog channel label).
"""
from __future__ import annotations

from copy import deepcopy

# ---------------------------------------------------------------------------
# Boards.  Pin numbers are labels, not assumptions: unknown boards are not
# assigned pins by the generator (a manual verification step is emitted).
# ---------------------------------------------------------------------------
BOARDS: dict[str, dict] = {
    "esp32": {
        "name": "ESP32 DevKit V1 (ESP32-WROOM-32)",
        "platform": "arduino",
        "logic_v": 3.3,
        "analog_max_v": 3.3,
        "voltage_note": "5 V on VIN via USB or regulator; GPIO is NOT 5 V tolerant. ADC1 only when Wi-Fi is active.",
        "i2c": {"SDA": "21", "SCL": "22"},
        "spi": {"SCK": "18", "MISO": "19", "MOSI": "23"},
        "cs_pool": ["5", "15", "2", "13"],
        "uart": {"RX": "16", "TX": "17"},
        "digital_pool": ["4", "16", "17", "25", "26", "27", "32", "33", "13", "14"],
        "analog_pool": ["34", "35", "32", "33"],
        "pwm_pool": ["25", "26", "27", "32", "33", "4", "16", "17"],
        "input_only": ["34", "35", "36", "39"],
        "reserved": ["0", "1", "3", "6", "7", "8", "9", "10", "11", "12"],
        "adc2": ["0", "2", "4", "12", "13", "14", "15", "25", "26", "27"],
        "gpio_current_ma": 12,
        "board_current_ma": 500,
        "docs": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/",
        "core": "esp32 by Espressif Systems (Arduino IDE Boards Manager, 3.x)",
        "upload": "Board: ESP32 Dev Module / 115200 baud / USB-UART bridge driver installed.",
    },
    "esp32s3": {
        "name": "ESP32-S3-DevKitC-1",
        "platform": "arduino",
        "logic_v": 3.3,
        "analog_max_v": 3.3,
        "voltage_note": "3.3 V GPIO only; USB-OTG port supports native USB CDC. Use ADC1 channels with Wi-Fi.",
        "i2c": {"SDA": "8", "SCL": "9"},
        "spi": {"SCK": "12", "MISO": "13", "MOSI": "11"},
        "cs_pool": ["10", "14", "15", "16"],
        "uart": {"RX": "18", "TX": "17"},
        "digital_pool": ["4", "5", "6", "7", "15", "16", "17", "18", "35", "36"],
        "analog_pool": ["1", "2", "3", "4"],
        "pwm_pool": ["4", "5", "6", "7", "15", "16"],
        "input_only": [],
        "reserved": ["0", "19", "20", "26", "27", "28", "29", "30", "31", "32", "33", "34", "43", "44", "46"],
        "adc2": ["11", "12", "13", "14"],
        "gpio_current_ma": 12,
        "board_current_ma": 500,
        "docs": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/",
        "core": "esp32 by Espressif Systems (3.x), select ESP32S3 Dev Module",
        "upload": "Select ESP32S3 Dev Module; enable USB CDC on boot if using the native USB port.",
    },
    "esp8266": {
        "name": "NodeMCU 1.0 (ESP-12E / ESP8266)",
        "platform": "arduino",
        "logic_v": 3.3,
        "analog_max_v": 1.0,
        "voltage_note": "Single A0 ADC with 0-1 V range (NodeMCU has an on-board divider for 0-3.3 V). GPIO is not 5 V tolerant.",
        "i2c": {"SDA": "D2", "SCL": "D1"},
        "spi": {"SCK": "D5", "MISO": "D6", "MOSI": "D7"},
        "cs_pool": ["D8", "D3", "D4"],
        "uart": {"RX": "D7", "TX": "D8"},
        "digital_pool": ["D0", "D3", "D4", "D5", "D6", "D7", "D8"],
        "analog_pool": ["A0"],
        "pwm_pool": ["D3", "D4", "D5", "D6"],
        "input_only": [],
        "reserved": ["D9", "D10"],
        "adc2": [],
        "gpio_current_ma": 12,
        "board_current_ma": 400,
        "docs": "https://arduino-esp8266.readthedocs.io/en/latest/",
        "core": "esp8266 by ESP8266 Community (3.x)",
        "upload": "Board: NodeMCU 1.0 (ESP-12E Module), 115200 baud.",
    },
    "uno": {
        "name": "Arduino Uno R3 (ATmega328P)",
        "platform": "arduino",
        "logic_v": 5.0,
        "analog_max_v": 5.0,
        "voltage_note": "5 V logic. 3.3 V-only I2C sensors REQUIRE a bidirectional level shifter.",
        "i2c": {"SDA": "A4", "SCL": "A5"},
        "spi": {"SCK": "13", "MISO": "12", "MOSI": "11"},
        "cs_pool": ["10", "9", "8", "7"],
        "uart": {"RX": "0", "TX": "1"},
        "digital_pool": ["2", "3", "4", "5", "6", "7", "8", "9"],
        "analog_pool": ["A0", "A1", "A2", "A3"],
        "pwm_pool": ["3", "5", "6", "9", "10", "11"],
        "input_only": [],
        "reserved": ["0", "1", "13"],
        "adc2": [],
        "gpio_current_ma": 20,
        "board_current_ma": 200,
        "docs": "https://docs.arduino.cc/hardware/uno-rev3",
        "core": "Arduino AVR Boards (built in)",
        "upload": "Board: Arduino Uno, 9600/115200 baud serial.",
    },
    "picow": {
        "name": "Raspberry Pi Pico W (RP2040)",
        "platform": "arduino",
        "logic_v": 3.3,
        "analog_max_v": 3.3,
        "voltage_note": "GPIO is 3.3 V only; ADC inputs must stay below 3.3 V. VBUS is 5 V.",
        "i2c": {"SDA": "4", "SCL": "5"},
        "spi": {"SCK": "18", "MISO": "16", "MOSI": "19"},
        "cs_pool": ["17", "20", "21", "22"],
        "uart": {"RX": "1", "TX": "0"},
        "digital_pool": ["2", "3", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "20", "21", "22"],
        "analog_pool": ["26", "27", "28"],
        "pwm_pool": ["2", "3", "6", "7", "8", "9", "10", "11"],
        "input_only": [],
        "reserved": ["23", "24", "25", "29"],
        "adc2": [],
        "gpio_current_ma": 12,
        "board_current_ma": 300,
        "docs": "https://datasheets.raspberrypi.com/picow/pico-w-datasheet.pdf",
        "core": "Raspberry Pi Pico/RP2040 by Earle Philhower (arduino-pico)",
        "upload": "Board: Raspberry Pi Pico W; BOOTSEL drag-and-drop or picotool.",
    },
    "rpi4": {
        "name": "Raspberry Pi 4 Model B (Linux host / gateway)",
        "platform": "linux_python",
        "logic_v": 3.3,
        "analog_max_v": 3.3,
        "voltage_note": "GPIO is 3.3 V and unbuffered. There is NO built-in ADC: use an external I2C ADC (e.g. ADS1115).",
        "i2c": {"SDA": "2", "SCL": "3"},
        "spi": {"SCK": "11", "MISO": "9", "MOSI": "10"},
        "cs_pool": ["8", "7"],
        "uart": {"RX": "15", "TX": "14"},
        "digital_pool": ["17", "18", "27", "22", "23", "24", "25", "5", "6", "12", "13", "16", "19", "20", "21", "26"],
        "analog_pool": [],
        "pwm_pool": ["18", "12", "13", "19"],
        "input_only": [],
        "reserved": ["0", "1", "14", "15"],
        "adc2": [],
        "gpio_current_ma": 16,
        "board_current_ma": 0,
        "docs": "https://www.raspberrypi.com/documentation/computers/raspberry-pi.html",
        "core": "Python 3 + gpiozero/smbus2 (system packages)",
        "upload": "Run as a systemd service; enable I2C/SPI via raspi-config where needed.",
    },
    "esp32cam": {
        "name": "AI-Thinker ESP32-CAM (OV2640)",
        "platform": "arduino",
        "logic_v": 3.3,
        "analog_max_v": 3.3,
        "voltage_note": "Needs a stable 5 V / >= 1 A supply at the 5 V pin; GPIO0 must be left free for boot and camera uses many pins.",
        "i2c": {"SDA": "14", "SCL": "15"},
        "spi": {"SCK": "12", "MISO": "13", "MOSI": "2"},
        "cs_pool": ["16"],
        "uart": {"RX": "3", "TX": "1"},
        "digital_pool": ["4", "12", "13", "16"],
        "analog_pool": [],
        "pwm_pool": ["4"],
        "input_only": [],
        "reserved": ["0", "1", "2", "3", "5", "6", "7", "8", "9", "10", "11", "14", "15"],
        "adc2": ["4", "12", "13"],
        "gpio_current_ma": 12,
        "board_current_ma": 700,
        "docs": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/",
        "core": "esp32 by Espressif Systems (3.x), select AI Thinker ESP32-CAM",
        "upload": "Use an external USB-TTL adapter; GPIO0 to GND while flashing.",
    },
}


def part(key, name, group, iface, signals, voltage, logic_v, current_ma,
         price, docs, *, alt="", notes="", libs=None, globs=None, setup=None,
         read=None, fields=None, calibration="", level_shift=False,
         mandatory=True, expr=None, address=""):
    """Declare a component. ``expr`` is used by the generic analog driver."""
    return dict(
        key=key, name=name, group=group, iface=iface, signals=signals,
        voltage=voltage, logic_v=logic_v, current_ma=current_ma,
        price_estimate=price, docs=docs, alternatives=alt, notes=notes,
        libs=libs or [], globs=globs or [], setup=setup or [], read=read or [],
        fields=fields or [], calibration=calibration, level_shift=level_shift,
        mandatory=mandatory, expr=expr, address=address,
    )


ALDOCS = "https://docs.arduino.cc/libraries/"


def analog(key, name, group, price, docs, expr, unit, field, *, voltage="3.3–5 V",
           logic_v=3.3, current_ma=8, notes="", calibration="", alt="", level_shift=False):
    """Analog sensor read through a board ADC with an explicit conversion."""
    return part(
        key, name, group, "analog", [("SIG", "analog_in")], voltage, logic_v,
        current_ma, price, docs, alt=alt, notes=notes, calibration=calibration,
        level_shift=level_shift, expr=expr,
        libs=[], globs=[], setup=["pinMode(@PIN@, INPUT);"],
        read=["int raw = analogRead(@PIN@);", f"float {field} = {expr};"],
        fields=[(field, unit)],
    )


PARTS: dict[str, dict] = {}


def P(*args, **kwargs):
    p = part(*args, **kwargs)
    PARTS[p["key"]] = p
    return p


# --- passives / power / protection -----------------------------------------
P("r220", "220 Ω resistor, 0.25 W", "Passive", "passive", [], "n/a", 0, 0,
  "$0.02–0.10 each (assumption: bulk resistor kit, 2024 street pricing)",
  "https://www.arduino.cc/en/Tutorial/BuiltInExamples/Blink", alt="150–330 Ω metal film",
  notes="Limits LED current. Verify with (Vcc - Vf) / I before substituting.",
  mandatory=True)
P("r10k", "10 kΩ resistor, 0.25 W", "Passive", "passive", [], "n/a", 0, 0,
  "$0.02–0.10 each (assumption: bulk resistor kit)",
  "https://docs.arduino.cc/learn/electronics/button-tutorial", alt="4.7 kΩ for 1-Wire",
  notes="Pull-up/pull-down or LDR divider half.")
P("r4k7", "4.7 kΩ resistor, 0.25 W", "Passive", "passive", [], "n/a", 0, 0,
  "$0.02–0.10 each (assumption: bulk resistor kit)",
  "https://www.analog.com/en/resources/technical-articles/guidelines-for-reliable-ds18b20-communication.html",
  alt="5.1 kΩ", notes="Required 1-Wire / I2C bus pull-up; verify bus capacitance for long cables.")
P("cap100", "100 µF / 10 V electrolytic capacitor", "Passive", "passive", [], "≥10 V", 0, 0,
  "$0.10–0.40 (assumption: common through-hole part)",
  "https://docs.arduino.cc/learn/electronics/level-shifter-tutorial",
  notes="Decoupling for motors, relays, pumps and WS2812B strips.")
P("level_shifter", "4-channel bidirectional logic level shifter (BSS138)", "Interface",
  "passive", [], "1.8–5 V", 0, 5, "$1–3 (assumption: breakout board)",
  "https://www.adafruit.com/product/757",
  notes="Mandatory for 5 V logic into 3.3 V GPIO. HV/LV reference rails must both be connected.")
P("buck5v", "5 V / 2 A DC-DC buck converter (or USB supply)", "Power", "power", [],
  "7–24 V in", 5.0, 0, "$3–8 (assumption: common module)",
  "https://docs.arduino.cc/learn/electronics/power-supplies",
  notes="Common ground with the controller is mandatory. Size for actuator stall current + 30 % headroom.")
P("mosfet", "IRLZ44N logic-level N-MOSFET + 220 Ω gate resistor", "Actuator", "digital",
  [("GATE", "digital_out")], "5 V load", 3.3, 0, "$1–3 (assumption: single MOSFET)",
  "https://www.adafruit.com/product/355", alt="IRLB8721, AO3400 module",
  notes="Gate threshold must be compatible with 3.3 V logic; a 10 kΩ gate-to-GND pulldown prevents phantom turn-on.",
  libs=[], setup=["pinMode(@PIN@, OUTPUT);", "digitalWrite(@PIN@, LOW);"],
  read=["// MOSFET gate is driven by the control logic below."])

# --- environmental sensing --------------------------------------------------
P("dht22", "DHT22 / AM2302 temperature & humidity sensor", "Sensor", "digital",
  [("DATA", "digital_in")], "3.3–6 V", 3.3, 2,
  "$4–8 (assumption: single breakout, generic marketplace price)",
  "https://www.adafruit.com/product/385", alt="SHT31 (I2C), BME280",
  notes="Needs a 10 kΩ pull-up on DATA (many breakouts include one). Minimum 2 s between samples.",
  libs=["DHT sensor library by Adafruit (1.4.x)", "Adafruit Unified Sensor (1.1.x)"],
  globs=["#define DHTPIN @PIN@", "#define DHTTYPE DHT22", "DHT dht(DHTPIN, DHTTYPE);"],
  setup=["dht.begin();"],
  read=["float temperature = dht.readTemperature();", "float humidity = dht.readHumidity();",
        "if (isnan(temperature) || isnan(humidity)) { Serial.println(F(\"[ERR] DHT22 read failed\")); return; }"],
  fields=[("temperature", "°C"), ("humidity", "%RH")],
  calibration="Compare against a reference hygrometer; apply an offset constant, do not 'calibrate' humidity with a single point.")
P("dht11", "DHT11 temperature & humidity sensor", "Sensor", "digital",
  [("DATA", "digital_in")], "3.3–5 V", 3.3, 2,
  "$2–4 (assumption: single breakout)",
  "https://www.arduino.cc/reference/en/libraries/dht-sensor-library/", alt="DHT22 (better accuracy)",
  notes="±2 °C, ±5 %RH, 1 Hz maximum. Intended for beginner demos only.",
  libs=["DHT sensor library by Adafruit (1.4.x)"],
  globs=["#define DHTPIN @PIN@", "#define DHTTYPE DHT11", "DHT dht(DHTPIN, DHTTYPE);"],
  setup=["dht.begin();"],
  read=["float temperature = dht.readTemperature();", "float humidity = dht.readHumidity();",
        "if (isnan(temperature) || isnan(humidity)) { Serial.println(F(\"[ERR] DHT11 read failed\")); return; }"],
  fields=[("temperature", "°C"), ("humidity", "%RH")],
  calibration="Educational only; cross-check with a known thermometer.")
P("bme280", "BME280 I2C temperature / humidity / pressure sensor", "Sensor", "i2c", [],
  "1.8–3.6 V (breakout with regulator: 3.3–5 V)", 3.3, 1,
  "$3–10 (assumption: breakout board)",
  "https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf",
  alt="BMP280 (no humidity), SHT31 + BMP280", address="0x76 (or 0x77 on some boards)",
  notes="3.3 V logic. Confirm the I2C address with an I2C scanner before trusting readings.",
  libs=["Adafruit BME280 Library (2.2.x)", "Adafruit Unified Sensor (1.1.x)"],
  globs=["Adafruit_BME280 bme;"],
  setup=["if (!bme.begin(0x76)) { Serial.println(F(\"[ERR] BME280 not found at 0x76 - try 0x77\")); }"],
  read=["float temperature = bme.readTemperature();", "float humidity = bme.readHumidity();",
        "float pressure = bme.readPressure() / 100.0F;  // hPa"],
  fields=[("temperature", "°C"), ("humidity", "%RH"), ("pressure", "hPa")],
  calibration="Pressure needs a local sea-level reference for altitude; humidity has a ±3 %RH tolerance.")
P("bme680", "BME680 I2C gas / VOC + climate sensor", "Sensor", "i2c", [],
  "1.7–3.6 V", 3.3, 12,
  "$12–22 (assumption: breakout)", "https://www.bosch-sensortec.com/products/environmental-sensors/gas-sensors/bme680/",
  alt="SGP30, CCS811", address="0x77 or 0x76",
  notes="Integrated heater draws current; IAQ index needs Bosch BSEC (closed binary) for absolute values. Raw gas resistance is usable without it.",
  libs=["Adafruit BME680 Library (2.0.x)"], globs=["Adafruit_BME680 bme;"],
  setup=["if (!bme.begin(0x77)) { Serial.println(F(\"[ERR] BME680 not found; scan I2C bus\")); }",
         "bme.setGasHeater(320, 150);  // 320 C for 150 ms"],
  read=["if (!bme.performReading()) { Serial.println(F(\"[ERR] BME680 read failed\")); return; }",
        "float temperature = bme.temperature;", "float humidity = bme.humidity;",
        "float gas_kohm = bme.gas_resistance / 1000.0F;"],
  fields=[("temperature", "°C"), ("humidity", "%RH"), ("gas_kohm", "kΩ")],
  calibration="Requires a 24–48 h burn-in and relative baseline tracking; do not report absolute IAQ without BSEC.")
P("sht31", "SHT31-D I2C temperature / humidity sensor", "Sensor", "i2c", [],
  "2.4–5.5 V", 3.3, 1, "$5–12 (assumption: breakout)",
  "https://sensirion.com/products/catalog/SHT31-DIS/", alt="SHT30, BME280", address="0x44 / 0x45",
  libs=["Adafruit SHT31 Library (2.2.x)"], globs=["Adafruit_SHT31 sht31 = Adafruit_SHT31();"],
  setup=["if (!sht31.begin(0x44)) { Serial.println(F(\"[ERR] SHT31 not found at 0x44\")); }"],
  read=["float temperature = sht31.readTemperature();", "float humidity = sht31.readHumidity();",
        "if (isnan(temperature)) { Serial.println(F(\"[ERR] SHT31 read failed\")); return; }"],
  fields=[("temperature", "°C"), ("humidity", "%RH")],
  calibration="±2 %RH; use a salt-solution reference check if accuracy matters.")
P("ds18b20", "DS18B20 waterproof 1-Wire temperature probe", "Sensor", "onewire",
  [("DATA", "digital_in")], "3.0–5.5 V", 3.3, 1, "$3–7 (assumption: cabled probe)",
  "https://www.analog.com/en/products/ds18b20.html", alt="DHT22 (air), NTC thermistor",
  notes="Requires a 4.7 kΩ pull-up between DATA and VCC; supports multiple sensors on one bus with ROM addressing.",
  libs=["OneWire (2.3.x)", "DallasTemperature (3.9.x)"],
  globs=["#define ONE_WIRE_BUS @PIN@", "OneWire oneWire(ONE_WIRE_BUS);", "DallasTemperature sensors(&oneWire);"],
  setup=["sensors.begin();", "sensors.setResolution(11);"],
  read=["sensors.requestTemperatures();", "float temperature = sensors.getTempCByIndex(0);",
        "if (temperature == DEVICE_DISCONNECTED_C) { Serial.println(F(\"[ERR] DS18B20 disconnected\")); return; }"],
  fields=[("temperature", "°C")], calibration="Ice-bath (0 °C) and boiling-point check; ±0.5 °C device tolerance.")
P("bh1750", "BH1750 I2C ambient light sensor (lux)", "Sensor", "i2c", [],
  "2.4–3.6 V", 3.3, 1, "$2–5 (assumption: GY-302 breakout)",
  "https://www.rohm.com/products/sensors/optical/light-sensors/bh1750", alt="TSL2561, LDR + ADC", address="0x23 / 0x5C",
  libs=["BH1750 by Christopher Laws (1.3.x)"], globs=["BH1750 lightMeter;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) { Serial.println(F(\"[ERR] BH1750 init failed\")); }"],
  read=["float lux = lightMeter.readLightLevel();",
        "if (lux < 0) { Serial.println(F(\"[ERR] BH1750 read failed\")); return; }"],
  fields=[("lux", "lx")], calibration="Compare with a calibrated lux meter; sensor response is cosine-corrected on quality breakouts.")
P("ldr", "Photoresistor (LDR) + 10 kΩ voltage divider", "Sensor", "analog",
  [("SIG", "analog_in")], "3.3–5 V", 3.3, 1, "$1–2 (assumption: kit part)",
  "https://docs.arduino.cc/learn/electronics/photocells", alt="BH1750 I2C lux sensor",
  notes="LDRs are non-linear and slow; use for threshold decisions, not precision lux.",
  libs=[], setup=["pinMode(@PIN@, INPUT);"],
  read=["int raw = analogRead(@PIN@);", "float light_raw = raw;  // 0..ADC_MAX, higher = brighter with divider to GND"],
  fields=[("light_raw", "ADC")], calibration="Record ADC at dark and bright conditions, then set two thresholds with hysteresis.")
P("ntc", "10 kΩ NTC thermistor + 10 kΩ divider", "Sensor", "analog",
  [("SIG", "analog_in")], "3.3 V", 3.3, 1, "$1–3 (assumption: kit part)",
  "https://docs.arduino.cc/learn/electronics/thermistor", alt="DS18B20, BME280",
  notes="Beta-coefficient approximation is adequate only over a limited range.",
  libs=[], setup=["pinMode(@PIN@, INPUT);"],
  read=["int raw = analogRead(@PIN@);",
        "float ratio = raw / (float)ADC_MAX;",
        "float resistance = 10000.0F * ratio / (1.0F - ratio);",
        "float temperature = 1.0F / (1.0F/298.15F + log(resistance/10000.0F)/3950.0F) - 273.15F;"],
  fields=[("temperature", "°C")], calibration="Verify the divider orientation and the B-value (3950 typical) in the part datasheet.")
P("uv", "ML8511 UV analog sensor", "Sensor", "analog", [("SIG", "analog_in")],
  "3.3 V", 3.3, 3, "$6–12 (assumption: breakout)",
  "https://www.sparkfun.com/products/12705", alt="VEML6075 I2C",
  libs=[], setup=["pinMode(@PIN@, INPUT);"],
  read=["int raw = analogRead(@PIN@);", "float uv_mw_cm2 = (raw / (float)ADC_MAX) * 3.3F * 5.0F;  // placeholder mapping, verify datasheet curve"],
  fields=[("uv_mw_cm2", "mW/cm²")],
  calibration="Use the datasheet output-voltage-to-UV curve; the linear 5.0 factor is an approximation to be replaced after bench check.")

# --- agriculture / water ----------------------------------------------------
analog_parts = [
    ("soil_cap", "Capacitive soil-moisture sensor v1.2", "Sensor", "$3–7 (assumption: breakout)",
     "https://www.seeedstudio.com/Grove-Capacitive-Moisture-Sensor-Corrosion-Resistant-p-4548.html",
     "map((float)raw, DRY_RAW, WET_RAW, 0.0F, 100.0F)", "%", "soil_pct",
     dict(calibration="Dry-air and submerged-water ADC values MUST be measured per sensor and stored in DRY_RAW/WET_RAW.",
          alt="VH400, resistive probe (shorter life)", notes="Prefer capacitive probes: resistive probes corrode and electrolyse soil.")),
    ("soil_res", "Resistive soil-moisture probe + comparator", "Sensor", "$1–3 (assumption: kit)",
     "https://docs.arduino.cc/learn/electronics/soil-moisture-sensor",
     "map((float)raw, DRY_RAW, WET_RAW, 0.0F, 100.0F)", "%", "soil_pct",
     dict(calibration="Two-point calibration required; expect drift from corrosion. Power the probe only during measurement.",
          notes="Drive probe power from a GPIO through a MOSFET to reduce corrosion.")),
    ("rain", "Rain sensor module (analog output)", "Sensor", "$2–5 (assumption: module)",
     "https://www.sparkfun.com/products/12707", "map((float)raw, DRY_RAW, WET_RAW, 0.0F, 100.0F)", "%", "rain_pct",
     dict(calibration="Record dry board value; wetness thresholds vary with water conductivity.",
          notes="Only the sensing plate may get wet. Never leave DC across the plate continuously.")),
    ("water_level", "Analog water-level / float sensor", "Sensor", "$2–6 (assumption: module)",
     "https://www.adafruit.com/product/3397", "map((float)raw, EMPTY_RAW, FULL_RAW, 0.0F, 100.0F)", "%", "level_pct",
     dict(calibration="Measure ADC with empty and full tank; store EMPTY_RAW/FULL_RAW in NVS.")),
    ("turbidity", "Turbidity sensor (analog, 0–4.5 V)", "Sensor", "$8–15 (assumption: module)",
     "https://www.dfrobot.com/product-1394.html", "(raw / (float)ADC_MAX) * 100.0F", "%", "turbidity_pct",
     dict(level_shift=True, notes="Output can exceed 3.3 V: use a resistor divider or level shifter on a 3.3 V ADC.",
          calibration="Real NTU requires calibration with formazin standards; this raw percentage is a relative index only.")),
    ("tds", "TDS / conductivity probe with analog board", "Sensor", "$10–20 (assumption: module)",
     "https://www.dfrobot.com/product-1074.html", "(raw / (float)ADC_MAX) * 3.3F * 500.0F", "ppm", "tds_ppm",
     dict(level_shift=True, calibration="Temperature compensation and a 1413 µS/cm standard solution are required for defensible ppm values.")),
    ("ph", "pH probe + analog interface board", "Sensor", "$15–35 (assumption: module)",
     "https://www.dfrobot.com/product-1110.html", "7.0F - ((raw / (float)ADC_MAX) * 3.3F - 2.5F) * 3.0F", "pH", "ph_value",
     dict(level_shift=True, calibration="Two-point calibration with pH 4.0 and pH 7.0 buffers is mandatory; probe drifts.")),
    ("pressure", "0–1 MPa analog pressure transducer (0.5–4.5 V)", "Sensor", "$12–25 (assumption: 5 V transducer)",
     "https://www.analog.com/en/products/mpl3115a2.html", "(raw / (float)ADC_MAX) * 3.3F * 2.0F", "bar", "pressure_bar",
     dict(level_shift=True, notes="Ratiometric 5 V output needs a divider; confirm actual transfer function from the vendor datasheet.")),
    ("water_leak", "Water-leak rope / probe with sense resistor", "Sensor", "$4–10 (assumption: kit)",
     "https://www.adafruit.com/product/3915", "(raw / (float)ADC_MAX) * 100.0F", "%", "leak_pct",
     dict(calibration="Measure dry and fully wetted ADC values; use a guarded AC excitation for permanent installs.")),
    ("gas_mq135", "MQ-135 analog air-quality/gas sensor", "Sensor", "$3–8 (assumption: module)",
     "https://www.pololu.com/product/2472", "(raw / (float)ADC_MAX) * 100.0F", "index", "gas_index",
     dict(level_shift=True, notes="Heater needs a stable 5 V and ~150 mA; 5 V analog output needs a divider for ESP32.",
          calibration="Requires 24–48 h burn-in and calibration in clean air; NOT a safety-certified gas detector.")),
    ("gas_mq2", "MQ-2 combustible-gas / smoke sensor", "Sensor", "$3–8 (assumption: module)",
     "https://www.pololu.com/product/2470", "(raw / (float)ADC_MAX) * 100.0F", "index", "gas_index",
     dict(level_shift=True, notes="Heater ~150 mA at 5 V. Educational indication only; never use as a life-safety alarm.",
          calibration="Baseline in clean air; MQ sensors are cross-sensitive to humidity and temperature.")),
    ("gas_mq7", "MQ-7 carbon-monoxide sensor", "Sensor", "$4–9 (assumption: module)",
     "https://www.sparkfun.com/products/9403", "(raw / (float)ADC_MAX) * 100.0F", "index", "co_index",
     dict(level_shift=True, notes="Requires the datasheet's 5 V/1.4 V heater duty cycle. EDUCATIONAL ONLY - certified CO alarm is mandatory for safety.",
          calibration="Requires controlled calibration gas; raw index is not a ppm measurement.")),
    ("sound", "Analog sound sensor (MAX9814 / LM393 module)", "Sensor", "$2–6 (assumption: module)",
     "https://www.adafruit.com/product/1713", "(raw / (float)ADC_MAX) * 100.0F", "index", "sound_index",
     dict(calibration="Set quiet-room baseline; for dB SPL you need a calibrated microphone and RMS windowing.")),
    ("vibration", "SW-420 vibration / knock sensor", "Sensor", "$1–3 (assumption: module)",
     "https://www.sparkfun.com/products/12916", "(raw / (float)ADC_MAX) * 100.0F", "index", "vib_index",
     dict(notes="A digital threshold module detects events, not magnitude; use an accelerometer for quantitative vibration.")),
    ("ntc_flow", "NTC + flow switch combo (temperature channel)", "Sensor", "$2–6 (assumption: kit)",
     "https://docs.arduino.cc/learn/electronics/thermistor", "(raw / (float)ADC_MAX) * 100.0F", "°C raw", "temp_raw", {}),
]
for key, name, group, price, docs, expr, unit, field, kw in analog_parts:
    PARTS[key] = analog(key, name, group, price, docs, expr, unit, field, **kw)

# --- distance / motion / presence -------------------------------------------
P("hcsr04", "HC-SR04 ultrasonic distance sensor", "Sensor", "digital",
  [("TRIG", "digital_out"), ("ECHO", "digital_in")], "5 V", 5.0, 15,
  "$2–5 (assumption: module)", "https://www.sparkfun.com/products/15569",
  alt="VL53L0X ToF, TFmini-S", level_shift=True,
  notes="ECHO is a 5 V pulse: a 1 kΩ/2 kΩ divider (or level shifter) is MANDATORY on 3.3 V GPIO.",
  libs=[], globs=["#define TRIG_PIN @TRIG@", "#define ECHO_PIN @ECHO@"],
  setup=["pinMode(TRIG_PIN, OUTPUT);", "pinMode(ECHO_PIN, INPUT);", "digitalWrite(TRIG_PIN, LOW);"],
  read=["digitalWrite(TRIG_PIN, LOW); delayMicroseconds(2);",
        "digitalWrite(TRIG_PIN, HIGH); delayMicroseconds(10);",
        "digitalWrite(TRIG_PIN, LOW);",
        "long dur = pulseIn(ECHO_PIN, HIGH, 30000UL);  // 30 ms timeout",
        "float distance_cm = (dur == 0) ? -1.0F : dur * 0.0343F / 2.0F;",
        "if (distance_cm < 0) { Serial.println(F(\"[ERR] HC-SR04 timeout - check ECHO divider\")); return; }"],
  fields=[("distance_cm", "cm")],
  calibration="Speed of sound changes ~0.6 m/s per °C; add temperature compensation for accuracy.")
P("vl53l0x", "VL53L0X I2C time-of-flight distance sensor", "Sensor", "i2c", [],
  "2.6–3.5 V", 3.3, 20, "$5–10 (assumption: breakout)",
  "https://www.st.com/en/imaging-and-photonics-solutions/vl53l0x.html", alt="VL53L1X (longer range), TFmini-S",
  libs=["VL53L0X by Pololu (1.3.x)"], globs=["VL53L0X tof;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!tof.init()) { Serial.println(F(\"[ERR] VL53L0X init failed\")); }", "tof.setTimeout(500);"],
  read=["float distance_cm = tof.readRangeSingleMillimeters() / 10.0F;",
        "if (tof.timeoutOccurred()) { Serial.println(F(\"[ERR] VL53L0X timeout\")); return; }"],
  fields=[("distance_cm", "cm")], calibration="Check target reflectivity; dark/glossy surfaces need a region-of-interest and longer timing budget.")
P("pir", "HC-SR501 PIR motion sensor", "Sensor", "digital",
  [("OUT", "digital_in")], "5–12 V (module regulator)", 3.3, 1,
  "$2–5 (assumption: module)", "https://www.adafruit.com/product/189",
  alt="mmWave radar (LD2410), RCWL-0516",
  notes="3.3 V output on most modules but verify with a multimeter. ~60 s warm-up, adjustable retrigger.",
  libs=[], globs=["#define PIR_PIN @PIN@"],
  setup=["pinMode(PIR_PIN, INPUT);", "Serial.println(F(\"[INFO] PIR warming up for 60 s\"));"],
  read=["bool motion = digitalRead(PIR_PIN) == HIGH;"],
  fields=[("motion", "bool")], calibration="Set sensitivity/time pots and verify detection zone physically.")
P("reed", "Reed switch / magnetic door contact", "Sensor", "digital",
  [("SIG", "digital_in")], "3.3 V", 3.3, 0,
  "$1–3 (assumption: pair)", "https://docs.arduino.cc/learn/electronics/button-tutorial",
  alt="Hall sensor A3144, MC-38 contact", notes="Use INPUT_PULLUP and wire the contact to GND; debounce in software.",
  libs=[], globs=["#define REED_PIN @PIN@"],
  setup=["pinMode(REED_PIN, INPUT_PULLUP);"],
  read=["bool door_open = digitalRead(REED_PIN) == HIGH;  // contact open with pull-up",
        "static bool lastDoor = !door_open;", "if (door_open != lastDoor) { delay(50); door_open = digitalRead(REED_PIN) == HIGH; lastDoor = door_open; }"],
  fields=[("door_open", "bool")], calibration="Verify normally-open vs normally-closed wiring with a continuity test.")
P("hall", "A3144 Hall-effect sensor / flow counter", "Sensor", "digital",
  [("SIG", "digital_in")], "4.5–24 V (open collector)", 3.3, 5,
  "$2–5 (assumption: YF-S201 hall flow sensor)", "https://www.seeedstudio.com/Grove-Water-Flow-Sensor-YF-S201.html",
  alt="Reed-switch flow meter", notes="Open-collector output needs a pull-up (INPUT_PULLUP works). Count pulses with an interrupt.",
  libs=[], globs=["#define HALL_PIN @PIN@", "volatile uint32_t flowPulses = 0;", "void IRAM_ATTR onFlowPulse() { flowPulses++; }"],
  setup=["pinMode(HALL_PIN, INPUT_PULLUP);", "attachInterrupt(digitalPinToInterrupt(HALL_PIN), onFlowPulse, FALLING);"],
  read=["noInterrupts(); uint32_t pulses = flowPulses; flowPulses = 0; interrupts();",
        "float flow_lpm = pulses / 7.5F;  // YF-S201: ~7.5 pulses/L/s x 60; verify vendor K-factor"],
  fields=[("flow_lpm", "L/min")], calibration="Measure the K-factor with a known volume; the 7.5 constant is a starting point.")
P("button", "Momentary push button (INPUT_PULLUP)", "Input", "digital",
  [("SIG", "digital_in")], "3.3 V", 3.3, 0, "$0.50–2 (assumption: kit)",
  "https://docs.arduino.cc/learn/electronics/button-tutorial", alt="TTP223 capacitive touch",
  libs=[], globs=["#define BUTTON_PIN @PIN@"],
  setup=["pinMode(BUTTON_PIN, INPUT_PULLUP);"],
  read=["bool pressed = digitalRead(BUTTON_PIN) == LOW;"],
  fields=[("pressed", "bool")], calibration="50 ms debounce; verify the switch is wired to GND, not VCC.")
P("touch", "TTP223 capacitive touch module", "Input", "digital",
  [("SIG", "digital_in")], "2.5–5.5 V", 3.3, 1, "$1–3 (assumption: module)",
  "https://www.adafruit.com/product/1374", alt="Physical button",
  libs=[], globs=["#define TOUCH_PIN @PIN@"], setup=["pinMode(TOUCH_PIN, INPUT);"],
  read=["bool touched = digitalRead(TOUCH_PIN) == HIGH;"], fields=[("touched", "bool")],
  calibration="Remove power supplies nearby if the output self-triggers.")

# --- gas / particles --------------------------------------------------------
P("pms5003", "PMS5003 / PMS7003 laser particle sensor (PM1/2.5/10)", "Sensor", "uart",
  [("RX", "uart_rx"), ("TX", "uart_tx")], "5 V", 3.3, 100,
  "$15–30 (assumption: module)", "https://www.adafruit.com/product/3686",
  alt="SDS011, SPS30", notes="5 V power, 3.3 V UART. Fan adds acoustic/airflow noise; use a 30 s warm-up.",
  libs=["Adafruit PM2.5 Sensor Library (1.1.x)"],
  globs=["Adafruit_PM25AQI aqi = Adafruit_PM25AQI();"],
  setup=["Serial2.begin(9600, SERIAL_8N1, @RX@, @TX@);", "if (!aqi.begin_UART(&Serial2)) { Serial.println(F(\"[ERR] PMS5003 not responding\")); }"],
  read=["PM25_AQI_Data_t data;", "if (!aqi.read(&data)) { Serial.println(F(\"[ERR] PM sensor read failed\")); return; }",
        "float pm25 = data.pm25_env;", "float pm10 = data.pm100_env;"],
  fields=[("pm25", "µg/m³"), ("pm10", "µg/m³")],
  calibration="Compare against a reference monitor; humidity > 70 %RH biases optical particle counts.")
P("sds011", "SDS011 UART laser PM2.5/PM10 sensor", "Sensor", "uart",
  [("RX", "uart_rx"), ("TX", "uart_tx")], "5 V", 3.3, 70,
  "$18–30 (assumption: module)", "https://www.sensor.community/en/sensors/dust-sensor-sds011/",
  alt="PMS5003, SPS30", notes="5 V power, 3.3 V UART; configure duty cycle to extend laser life.",
  libs=["SDS011 sensor library (0.0.x, e.g. ricki-z/SDS011)"],
  globs=["#include <SDS011.h>", "SDS011 sds;"],
  setup=["Serial2.begin(9600, SERIAL_8N1, @RX@, @TX@);", "sds.begin(&Serial2);"],
  read=["float pm25, pm10;", "int err = sds.read(&pm25, &pm10);",
        "if (err) { Serial.println(F(\"[ERR] SDS011 read/CRC failed\")); return; }"],
  fields=[("pm25", "µg/m³"), ("pm10", "µg/m³")], calibration="Co-locate with a reference station; apply humidity correction above 70 %RH.")
P("ccs811", "CCS811 I2C eCO2 / TVOC sensor", "Sensor", "i2c", [],
  "1.8–3.6 V", 3.3, 30, "$10–20 (assumption: breakout)",
  "https://www.sciosense.com/products/environmental-sensors/ccs811-gas-sensor-solution/",
  alt="SGP30, BME680", address="0x5A / 0x5B",
  libs=["Adafruit CCS811 Library (1.1.x)"], globs=["Adafruit_CCS811 ccs;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!ccs.begin(0x5A)) { Serial.println(F(\"[ERR] CCS811 not found at 0x5A\")); }",
         "ccs.setDriveMode(CCS811_DRIVE_MODE_60SEC);"],
  read=["if (!ccs.available()) return;", "if (ccs.readData()) { Serial.println(F(\"[ERR] CCS811 read error\")); return; }",
        "float co2 = ccs.geteCO2();", "float tvoc = ccs.getTVOC();"],
  fields=[("co2", "ppm eCO2"), ("tvoc", "ppb")],
  calibration="eCO2 is an ESTIMATE from VOC, not NDIR CO2. 48 h burn-in and baseline persistence needed.")
P("scd30", "SCD30 NDIR CO2 / temperature / humidity sensor", "Sensor", "i2c", [],
  "3.3–5.5 V", 3.3, 19, "$30–55 (assumption: breakout)",
  "https://sensirion.com/products/catalog/SCD30/", alt="SCD41, MH-Z19B", address="0x61",
  libs=["Adafruit SCD30 (1.0.x)"], globs=["Adafruit_SCD30 scd30;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!scd30.begin(0x61)) { Serial.println(F(\"[ERR] SCD30 not found\")); }",
         "scd30.setMeasurementInterval(30);"],
  read=["if (!scd30.dataReady()) return;", "if (!scd30.read()) { Serial.println(F(\"[ERR] SCD30 read failed\")); return; }",
        "float co2 = scd30.CO2;", "float temperature = scd30.temperature;", "float humidity = scd30.relative_humidity;"],
  fields=[("co2", "ppm"), ("temperature", "°C"), ("humidity", "%RH")],
  calibration="Enable automatic self-calibration only in periodically fresh-air environments; otherwise use forced recalibration at 400 ppm.")

# --- metrology / power / industrial -----------------------------------------
P("ina219", "INA219 I2C voltage / current monitor", "Sensor", "i2c", [],
  "3–5.5 V", 3.3, 1, "$3–8 (assumption: breakout)",
  "https://www.ti.com/product/INA219", alt="INA226, INA3221", address="0x40–0x4F",
  notes="High-side sensing with a shunt. Do not exceed the breakout's bus voltage; this is LOW-VOLTAGE DC only.",
  libs=["Adafruit INA219 (1.2.x)"], globs=["Adafruit_INA219 ina219;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!ina219.begin()) { Serial.println(F(\"[ERR] INA219 not found\")); }"],
  read=["float voltage_v = ina219.getBusVoltage_V();", "float current_ma = ina219.getCurrent_mA();",
        "float power_w = (voltage_v * current_ma) / 1000.0F;"],
  fields=[("voltage_v", "V"), ("current_ma", "mA"), ("power_w", "W")],
  calibration="Set the correct shunt resistance in the library config; zero the offset with no load.")
P("acs712", "ACS712 Hall-effect current sensor (5 A/20 A/30 A)", "Sensor", "analog",
  [("SIG", "analog_in")], "5 V", 5.0, 13, "$4–9 (assumption: module)",
  "https://www.allegromicro.com/en/products/sense/current-sensor-ics/zero-to-fifty-amp-integrated-conductor-sensor-ics/acs712",
  alt="INA219 (low-voltage DC), SCT-013 (AC, isolated)", level_shift=True,
  notes="5 V analog output centred at VCC/2; a divider is MANDATORY for 3.3 V ADCs. MAINS WIRING IS OUT OF SCOPE - use a certified module and an electrician for mains.",
  libs=[], setup=["pinMode(@PIN@, INPUT);"],
  read=["int raw = analogRead(@PIN@);",
        "float volts = (raw / (float)ADC_MAX) * VREF;",
        "float current_a = (volts - VREF/2.0F) / ACS_SENSITIVITY;  // 0.185 V/A for ACS712-05B",
        "float power_w = current_a * LOAD_VOLTAGE;"],
  fields=[("current_a", "A"), ("power_w", "W")],
  calibration="Measure zero-current offset and store it; verify sensitivity variant from the part marking.")
P("pzem", "PZEM-004T AC energy module (isolated, educational)", "Sensor", "uart",
  [("RX", "uart_rx"), ("TX", "uart_tx")], "5 V", 5.0, 15,
  "$12–25 (assumption: v3 module)", "https://innovatorsguru.com/pzem-004t-v3/",
  alt="Isolated CT clamp + ADC", level_shift=True,
  notes="MAINS VOLTAGE: the measurement side must be wired by a qualified person inside an insulated enclosure. 5 V logic needs shifting on 3.3 V MCUs.",
  libs=["PZEM004Tv30 by Jakub Mandula (1.1.x)"],
  globs=["#include <PZEM004Tv30.h>", "PZEM004Tv30 pzem(&Serial2);"],
  setup=["Serial2.begin(9600, SERIAL_8N1, @RX@, @TX@);"],
  read=["float voltage_v = pzem.voltage();", "float current_a = pzem.current();", "float power_w = pzem.power();",
        "if (isnan(voltage_v)) { Serial.println(F(\"[ERR] PZEM not responding; check 5 V and UART level\")); return; }"],
  fields=[("voltage_v", "V"), ("current_a", "A"), ("power_w", "W")],
  calibration="Compare the readout against a certified plug-in meter; never rely on it for billing or safety.")
P("hx711", "HX711 load-cell amplifier + strain gauge", "Sensor", "digital",
  [("DT", "digital_in"), ("SCK", "digital_out")], "2.7–5.5 V", 3.3, 2,
  "$5–12 (assumption: 5 kg cell + board)", "https://www.sparkfun.com/products/13879",
  alt="NAU7802 I2C", libs=["HX711 by Bogdan Necula (0.7.x)"],
  globs=["#include <HX711.h>", "HX711 scale;"],
  setup=["scale.begin(@DT@, @SCK@);", "scale.set_scale(CAL_FACTOR);", "scale.tare();"],
  read=["float weight_g = scale.get_units(5);",
        "if (isnan(weight_g)) { Serial.println(F(\"[ERR] HX711 no data - check DT/SCK\")); return; }"],
  fields=[("weight_g", "g")], calibration="Tare with no load, then compute CAL_FACTOR from a known calibration mass.")
P("mpu6050", "MPU6050 6-axis IMU (accelerometer + gyroscope)", "Sensor", "i2c", [],
  "3–5 V (breakout)", 3.3, 4, "$3–8 (assumption: GY-521)",
  "https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/",
  alt="ICM42688, BNO055", address="0x68 / 0x69",
  libs=["Adafruit MPU6050 (2.2.x)"], globs=["Adafruit_MPU6050 mpu;", "sensors_event_t a, g, tempEvt;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!mpu.begin(0x68)) { Serial.println(F(\"[ERR] MPU6050 not found\")); }",
         "mpu.setAccelerometerRange(MPU6050_RANGE_4_G);"],
  read=["mpu.getEvent(&a, &g, &tempEvt);", "float ax = a.acceleration.x; float ay = a.acceleration.y; float az = a.acceleration.z;",
        "float vibration_g = sqrt(ax*ax + ay*ay + az*az) / 9.81F;"],
  fields=[("ax", "m/s²"), ("ay", "m/s²"), ("az", "m/s²"), ("vibration_g", "g")],
  calibration="Six-position static calibration for offsets; temperature drift is significant.")
P("max30102", "MAX30102 pulse-oximetry / heart-rate sensor", "Sensor", "i2c", [],
  "1.8–3.3 V (breakout 3.3–5 V)", 3.3, 20, "$5–12 (assumption: module)",
  "https://www.analog.com/en/products/max30102.html", alt="MAX30105, AD8232 ECG (educational)",
  address="0x57", libs=["SparkFun MAX3010x Sensor Library (1.1.x)"],
  globs=["#include <MAX30105.h>", "MAX30105 particleSensor;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) { Serial.println(F(\"[ERR] MAX30102 not found\")); }",
         "particleSensor.setup(); particleSensor.setPulseAmplitudeRed(0x0A);"],
  read=["long irValue = particleSensor.getIR();", "float bpm = 0.0F;  // computed by peak-detection logic below",
        "if (irValue < 50000L) { Serial.println(F(\"[WARN] No finger detected\")); return; }"],
  fields=[("irValue", "counts"), ("bpm", "bpm (estimate)")],
  calibration="EDUCATIONAL WELLNESS PROTOTYPE ONLY. Not a medical device; SpO2 requires clinical calibration and regulatory approval.")
P("mlx90614", "MLX90614 non-contact IR thermometer", "Sensor", "i2c", [],
  "3.3–5 V", 3.3, 2, "$8–18 (assumption: GY-906)",
  "https://www.melexis.com/en/product/MLX90614/Digital-Plug-Play-Infrared-Thermometer",
  alt="MLX90640 thermal array", address="0x5A", libs=["Adafruit MLX90614 Library (2.1.x)"],
  globs=["Adafruit_MLX90614 mlx = Adafruit_MLX90614();"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!mlx.begin()) { Serial.println(F(\"[ERR] MLX90614 not found\")); }"],
  read=["float obj_temp = mlx.readObjectTempC();", "float amb_temp = mlx.readAmbientTempC();"],
  fields=[("obj_temp", "°C"), ("amb_temp", "°C")],
  calibration="Set emissivity correctly; shiny metal surfaces read low. Not for medical diagnosis.")
P("gps", "NEO-6M / NEO-8M GPS module (UART)", "Sensor", "uart",
  [("RX", "uart_rx"), ("TX", "uart_tx")], "3.3–5 V", 3.3, 45,
  "$8–18 (assumption: module + antenna)", "https://www.u-blox.com/en/product/neo-6-series",
  alt="NEO-M8N, SAM-M10Q", libs=["TinyGPS++ by Mikal Hart (1.0.x)"],
  globs=["#include <TinyGPS++.h>", "TinyGPSPlus gps;"],
  setup=["Serial2.begin(9600, SERIAL_8N1, @RX@, @TX@);"],
  read=["while (Serial2.available()) gps.encode(Serial2.read());",
        "bool gpsFix = gps.location.isValid();",
        "double lat = gpsFix ? gps.location.lat() : 0.0;",
        "double lng = gpsFix ? gps.location.lng() : 0.0;",
        "if (!gpsFix) { Serial.println(F(\"[WARN] No GPS fix; coordinates marked invalid\")); }"],
  fields=[("lat", "deg"), ("lng", "deg")],
  calibration="Cold-start fix can take minutes; use an outdoor view of the sky and check antenna orientation.")
P("rfid", "MFRC522 13.56 MHz RFID / NFC reader", "Sensor", "spi",
  [("CS", "spi_cs")], "2.5–3.3 V", 3.3, 26,
  "$4–9 (assumption: module)", "https://www.nxp.com/docs/en/data-sheet/MFRC522.pdf",
  alt="PN532 (I2C/SPI)", libs=["MFRC522 by GithubCommunity (1.4.x)"],
  globs=["#include <MFRC522.h>", "MFRC522 rfid(@CS@, UINT8_MAX);  // RST unused / tied to 3V3"],
  setup=["SPI.begin(@SCK@, @MISO@, @MOSI@, @CS@);", "rfid.PCD_Init();", "rfid.PCD_DumpVersionToSerial();"],
  read=["String uid = \"\";",
        "if (rfid.PICC_IsNewCardPresent() && rfid.PICC_ReadCardSerial()) {",
        "  for (byte i = 0; i < rfid.uid.size; i++) uid += String(rfid.uid.uidByte[i], HEX);",
        "  rfid.PICC_HaltA();",
        "}"],
  fields=[("uid", "hex string")],
  calibration="UID alone is not authentication - use cryptographic challenge/response for access control.")
P("rtc", "DS3231 I2C precision RTC + EEPROM", "Sensor", "i2c", [],
  "2.3–5.5 V", 3.3, 1, "$3–8 (assumption: module)",
  "https://www.analog.com/en/products/ds3231.html", alt="PCF8523, GPS time", address="0x68",
  libs=["RTClib by Adafruit (2.1.x)"], globs=["RTC_DS3231 rtc;"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!rtc.begin()) { Serial.println(F(\"[ERR] DS3231 not found\")); }",
         "// rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));  // run once, then comment out"],
  read=["DateTime now = rtc.now();", "char timestamp[20];", "snprintf(timestamp, sizeof(timestamp), \"%04u-%02u-%02uT%02u:%02u:%02u\", now.year(), now.month(), now.day(), now.hour(), now.minute(), now.second());"],
  fields=[("timestamp", "ISO-like")],
  calibration="Trim the aging register against a time source; remove the coin cell if the module is shipped with a flat one.")
P("sdcard", "microSD card SPI module + 8 GB card", "Storage", "spi",
  [("CS", "spi_cs")], "3.3 V (module regulator 5 V)", 3.3, 100,
  "$5–12 (assumption: module + card)", "https://www.arduino.cc/reference/en/libraries/sd/",
  alt="LittleFS on MCU flash, FRAM", libs=["SD (Arduino core)"],
  globs=["#include <SD.h>"],
  setup=["SPI.begin(@SCK@, @MISO@, @MOSI@, @CS@);", "if (!SD.begin(@CS@)) { Serial.println(F(\"[ERR] SD init failed - check 3.3 V and CS\")); }"],
  read=["File f = SD.open(\"/log.csv\", FILE_APPEND);", "if (f) { f.println(logLine); f.close(); } else { Serial.println(F(\"[ERR] SD write failed\")); }"],
  fields=[], notes="Use FAT32, keep writes buffered, and never remove power during a write.")

# --- actuators / indication -------------------------------------------------
P("led", "5 mm LED (any colour) + 220 Ω resistor", "Actuator", "digital",
  [("ANODE", "digital_out")], "3.3 V", 3.3, 8, "$0.20–1 (assumption: kit)",
  "https://docs.arduino.cc/learn/electronics/led-basics", alt="On-board GPIO2 LED",
  notes="Series resistor is MANDATORY. Wire anode to GPIO through resistor, cathode to GND.",
  libs=[], globs=["#define LED_PIN @PIN@"], setup=["pinMode(LED_PIN, OUTPUT);", "digitalWrite(LED_PIN, LOW);"],
  read=["// LED state set by control logic below"])
P("ws2812b", "WS2812B / NeoPixel RGB LED strip (8 LEDs)", "Actuator", "digital",
  [("DIN", "digital_out")], "5 V", 5.0, 480,
  "$5–15 (assumption: 8-LED stick)", "https://learn.adafruit.com/adafruit-neopixel-uberguide",
  alt="APA102, discrete RGB LED", level_shift=True,
  notes="5 V power with common ground; 3.3 V data often works but a 74AHCT125 level shifter is recommended. Add 1000 µF across power and 330 Ω in data.",
  libs=["Adafruit NeoPixel (1.12.x)"],
  globs=["#include <Adafruit_NeoPixel.h>", "Adafruit_NeoPixel strip(8, @PIN@, NEO_GRB + NEO_KHZ800);"],
  setup=["strip.begin();", "strip.setBrightness(60);", "strip.show();"],
  read=["// strip colour set by control logic below"])
P("buzzer", "Active piezo buzzer (3.3–5 V)", "Actuator", "digital",
  [("SIG", "digital_out")], "3.3–5 V", 3.3, 25, "$1–3 (assumption: module)",
  "https://docs.arduino.cc/learn/electronics/buzzer-basics", alt="Passive buzzer + PWM tone()",
  libs=[], globs=["#define BUZZER_PIN @PIN@"],
  setup=["pinMode(BUZZER_PIN, OUTPUT);", "digitalWrite(BUZZER_PIN, LOW);"],
  read=["// buzzer state set by control logic below"])
P("relay", "5 V single-channel relay module (optocoupler, active-LOW)", "Actuator", "digital",
  [("IN", "digital_out")], "5 V coil", 5.0, 75, "$2–5 (assumption: module)",
  "https://www.arduino.cc/en/Tutorial/PhysicalComputingExamples/Relay",
  alt="Logic-level MOSFET for DC loads", level_shift=True,
  notes="Most modules are ACTIVE-LOW and need a separate 5 V supply. MAINS CONTACT IS DANGEROUS: this curriculum uses the relay only for low-voltage DC loads. A qualified electrician and an enclosed, fused, certified relay are mandatory for mains.",
  libs=[], globs=["#define RELAY_PIN @PIN@"],
  setup=["pinMode(RELAY_PIN, OUTPUT);", "digitalWrite(RELAY_PIN, HIGH);  // active-LOW: start OFF"],
  read=["// relay state set by control logic below"])
P("servo", "SG90 / MG995 servo (PWM)", "Actuator", "pwm",
  [("PWM", "pwm_out")], "4.8–6 V", 3.3, 250, "$3–10 (assumption: micro servo)",
  "https://docs.arduino.cc/learn/electronics/servo-motors", alt="Stepper + driver",
  notes="Servo power must NOT come from the MCU 3.3 V rail. Common ground + separate 5 V / 1 A supply + 100 µF cap.",
  libs=["ESP32Servo (0.9.x) on ESP32 / Servo (built-in) on AVR"],
  globs=["#include <ESP32Servo.h>", "Servo actuator;"],
  setup=["actuator.attach(@PIN@, 500, 2400);", "actuator.write(0);"],
  read=["// servo angle set by control logic below"])
P("pump", "5 V submersible mini water pump + MOSFET driver", "Actuator", "digital",
  [("CTRL", "digital_out")], "5 V", 3.3, 300, "$4–10 (assumption: kit pump)",
  "https://www.adafruit.com/product/4540", alt="Peristaltic pump, solenoid valve",
  notes="Inductive kickback: a flyback diode (1N4007) across the pump terminals is MANDATORY. Never drive directly from GPIO.",
  libs=[], globs=["#define PUMP_PIN @PIN@"],
  setup=["pinMode(PUMP_PIN, OUTPUT);", "digitalWrite(PUMP_PIN, LOW);"],
  read=["// pump state set by control logic below"])
P("valve", "12 V solenoid water valve + MOSFET driver", "Actuator", "digital",
  [("CTRL", "digital_out")], "12 V", 3.3, 500, "$8–20 (assumption: valve + supply)",
  "https://www.adafruit.com/product/997", alt="5 V pump, servo ball valve",
  notes="Flyback diode required across the coil; use a separate 12 V supply and common ground.",
  libs=[], globs=["#define VALVE_PIN @PIN@"],
  setup=["pinMode(VALVE_PIN, OUTPUT);", "digitalWrite(VALVE_PIN, LOW);"],
  read=["// valve state set by control logic below"])
P("fan", "5 V DC fan + MOSFET driver", "Actuator", "digital",
  [("CTRL", "digital_out")], "5 V", 3.3, 200, "$3–8 (assumption: 80 mm fan)",
  "https://www.adafruit.com/product/4468", alt="PWM fan with 4-pin control",
  libs=[], globs=["#define FAN_PIN @PIN@"],
  setup=["pinMode(FAN_PIN, OUTPUT);", "digitalWrite(FAN_PIN, LOW);"],
  read=["// fan state set by control logic below"])
P("oled", "SSD1306 128x64 I2C OLED display", "Display", "i2c", [],
  "3.3–5 V (breakout)", 3.3, 20, "$5–10 (assumption: 0.96 in module)",
  "https://learn.adafruit.com/monochrome-oled-breakouts", alt="LCD1602 I2C, e-paper", address="0x3C",
  libs=["Adafruit SSD1306 (2.5.x)", "Adafruit GFX Library (1.11.x)"],
  globs=["#include <Adafruit_SSD1306.h>", "Adafruit_SSD1306 display(128, 64, &Wire, -1);"],
  setup=["Wire.begin(@SDA@, @SCL@);", "if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) { Serial.println(F(\"[ERR] OLED not found\")); }",
         "display.clearDisplay(); display.setTextSize(1); display.setTextColor(SSD1306_WHITE);"],
  read=["display.clearDisplay(); display.setCursor(0,0);", "display.println(displayLine);", "display.display();"],
  fields=[])
P("lcd", "LCD1602 with I2C backpack (PCF8574)", "Display", "i2c", [],
  "5 V", 5.0, 30, "$5–10 (assumption: module)",
  "https://www.arduino.cc/en/Reference/LiquidCrystal", alt="SSD1306 OLED (3.3 V)",
  address="0x27 or 0x3F", level_shift=True,
  libs=["LiquidCrystal I2C by Frank de Brabander (1.1.x)"],
  globs=["#include <LiquidCrystal_I2C.h>", "LiquidCrystal_I2C lcd(0x27, 16, 2);"],
  setup=["Wire.begin(@SDA@, @SCL@);", "lcd.init(); lcd.backlight();"],
  read=["lcd.clear(); lcd.setCursor(0,0); lcd.print(displayLine.substring(0,16));"], fields=[])
P("eink", "2.9 in SPI e-paper display", "Display", "spi",
  [("CS", "spi_cs"), ("DC", "digital_out"), ("RST", "digital_out")], "3.3 V", 3.3, 25,
  "$12–25 (assumption: module)", "https://www.waveshare.com/wiki/2.9inch_e-Paper_Module",
  alt="SSD1306 OLED", libs=["GxEPD2 by Jean-Marc Zingg (1.5.x)"],
  globs=["#include <GxEPD2_BW.h>", "// See GxEPD2 display selection for the exact panel class"],
  setup=["SPI.begin(@SCK@, @MISO@, @MOSI@, @CS@);", "// epd.init(); epd.setRotation(1);"],
  read=["// epd.display() is called by the render logic below"],
  fields=[], notes="Partial refresh has ghosting; do a full refresh periodically.")

# --- communications ---------------------------------------------------------
P("lora", "SX1278 / RFM95 LoRa SPI transceiver (868/915 MHz)", "Comms", "spi",
  [("CS", "spi_cs"), ("RST", "digital_out"), ("DIO0", "digital_in")], "1.8–3.7 V", 3.3, 120,
  "$8–16 (assumption: module)", "https://www.semtech.com/products/wireless-rf/lora-connect/sx1276",
  alt="SX1262, RFM69", notes="ANTENNA IS MANDATORY before transmitting. Use the region-correct ISM frequency and duty-cycle limits.",
  libs=["LoRa by Sandeep Mistry (0.8.x)"],
  globs=["#include <LoRa.h>"],
  setup=["SPI.begin(@SCK@, @MISO@, @MOSI@, @CS@);", "LoRa.setPins(@CS@, @RST@, @DIO0@);",
         "if (!LoRa.begin(868E6)) { Serial.println(F(\"[ERR] LoRa init failed - check wiring/antenna\")); }",
         "LoRa.setTxPower(14); LoRa.setSpreadingFactor(9);"],
  read=["LoRa.beginPacket(); LoRa.print(payload); LoRa.endPacket();",
        "Serial.println(F(\"[TX] LoRa packet sent\"));"])

P("nrf24", "nRF24L01+ 2.4 GHz SPI transceiver", "Comms", "spi",
  [("CS", "spi_cs"), ("CE", "digital_out")], "1.9–3.6 V", 3.3, 14,
  "$3–8 (assumption: module + adapter)", "https://nrf24.github.io/RF24/",
  alt="ESP-NOW (ESP32 built-in)", notes="Needs a solid 3.3 V supply with a 10 µF cap across the module pins.",
  libs=["RF24 by TMRh20 (1.4.x)"],
  globs=["#include <RF24.h>", "RF24 radio(@CE@, @CS@);"],
  setup=["SPI.begin(@SCK@, @MISO@, @MOSI@, @CS@);",
         "if (!radio.begin()) { Serial.println(F(\"[ERR] nRF24L01 not responding\")); }",
         "radio.setPALevel(RF24_PA_LOW); radio.openWritingPipe(0xF0F0F0F0E1LL);"],
  read=["bool ok = radio.write(&payload, sizeof(payload));",
        "Serial.println(ok ? F(\"[TX] nRF24 OK\") : F(\"[ERR] nRF24 TX failed\"));"])
P("gsm", "SIM800L / SIM7600 cellular module (2G/4G)", "Comms", "uart",
  [("RX", "uart_rx"), ("TX", "uart_tx")], "3.4–4.4 V (2 A peaks)", 3.3, 2000,
  "$12–35 (assumption: module + SIM)", "https://www.simcom.com/product/SIM800L/",
  alt="NB-IoT / LTE-M modem, LoRaWAN gateway", level_shift=True,
  notes="Needs a dedicated 2 A peak supply (LiPo + buck). 2G networks are shut down in many countries - check local coverage.",
  libs=["TinyGSM by Volodymyr Shymanskyy (0.11.x)"],
  globs=["#define TINY_GSM_MODEM_SIM800", "#include <TinyGsmClient.h>", "TinyGsm modem(Serial2);"],
  setup=["Serial2.begin(9600, SERIAL_8N1, @RX@, @TX@);", "modem.restart();",
         "if (!modem.waitForNetwork()) { Serial.println(F(\"[ERR] No cellular network\")); }"],
  read=["if (!modem.isNetworkConnected()) { Serial.println(F(\"[WARN] cellular reconnect needed\")); }"])
P("rs485", "MAX485 / SP3485 RS-485 transceiver (Modbus RTU)", "Comms", "uart",
  [("RX", "uart_rx"), ("TX", "uart_tx"), ("DE", "digital_out")], "3.3–5 V", 3.3, 30,
  "$3–8 (assumption: module)", "https://www.analog.com/en/products/max485.html",
  alt="CAN bus (MCP2515), Ethernet", libs=["ModbusMaster by Doc Walker (2.0.x)"],
  globs=["#include <ModbusMaster.h>", "ModbusMaster node;", "#define DE_PIN @DE@"],
  setup=["Serial2.begin(9600, SERIAL_8N1, @RX@, @TX@);", "pinMode(DE_PIN, OUTPUT); digitalWrite(DE_PIN, LOW);",
         "node.begin(1, Serial2);"],
  read=["uint8_t result = node.readHoldingRegisters(0x0000, 2);",
        "if (result != node.ku8MBSuccess) { Serial.println(F(\"[ERR] Modbus RTU read failed\")); return; }",
        "float reg_value = node.getResponseBuffer(0);"],
  fields=[("reg_value", "raw")],
  notes="Terminate the bus with 120 Ω at both ends; DE must be HIGH while transmitting.")
P("ethernet", "W5500 SPI Ethernet module", "Comms", "spi",
  [("CS", "spi_cs")], "3.3 V", 3.3, 130, "$8–15 (assumption: module)",
  "https://www.wiznet.io/product-item/w5500/", alt="ESP32 native Wi-Fi, ENC28J60",
  libs=["Ethernet (Arduino core, 2.x)"], globs=["#include <Ethernet.h>", "byte mac[] = {0xDE,0xAD,0xBE,0xEF,0xFE,0x01};"],
  setup=["Ethernet.init(@CS@);", "if (Ethernet.begin(mac) == 0) { Serial.println(F(\"[ERR] DHCP failed\")); }"],
  read=["if (Ethernet.linkStatus() != LinkON) { Serial.println(F(\"[WARN] Ethernet link down\")); }"],
  fields=[])
P("canbus", "MCP2515 SPI CAN controller + TJA1050", "Comms", "spi",
  [("CS", "spi_cs")], "5 V (module)", 3.3, 60, "$6–12 (assumption: module)",
  "https://www.microchip.com/en-us/product/MCP2515", alt="Built-in TWAI on ESP32 + transceiver", level_shift=True,
  libs=["mcp_can by Cory Fowler (1.5.x)"], globs=["#include <mcp_can.h>", "MCP_CAN CAN0(@CS@);"],
  setup=["SPI.begin(@SCK@, @MISO@, @MOSI@, @CS@);",
         "if (CAN0.begin(MCP_ANY, CAN_500KBPS, MCP_8MHZ) != CAN_OK) { Serial.println(F(\"[ERR] MCP2515 init failed\")); }"],
  read=["byte data[8] = {0}; byte len = 0;",
        "if (CAN0.checkReceive() == CAN_MSGAVAIL) { CAN0.readMsgBuf(&len, data); Serial.println(F(\"[RX] CAN frame\")); }"],
  fields=[])

# --- camera / audio / biometrics --------------------------------------------
P("camera", "OV2640 camera (on ESP32-CAM)", "Sensor", "camera", [], "3.3 V", 3.3, 150,
  "$6–12 (assumption: ESP32-CAM board)", "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/",
  alt="USB webcam on Raspberry Pi", libs=["esp32-camera (Arduino ESP32 core examples)"],
  globs=["#include \"esp_camera.h\"", "camera_fb_t *fb = NULL;"],
  setup=["// camera_config_t from the ESP32-CAM CameraWebServer example; init with esp_camera_init(&config)"],
  read=["fb = esp_camera_fb_get();", "if (!fb) { Serial.println(F(\"[ERR] Camera capture failed\")); return; }",
        "size_t jpeg_bytes = fb->len;", "esp_camera_fb_return(fb);"],
  fields=[("jpeg_bytes", "bytes")])
P("mic_i2s", "INMP441 I2S MEMS microphone", "Sensor", "i2s",
  [("WS", "digital_out"), ("SD", "digital_in"), ("SCK", "digital_out")], "1.6–3.6 V", 3.3, 2,
  "$4–9 (assumption: module)", "https://invensense.tdk.com/products/audiosolutions/inmp441/",
  alt="MAX9814 analog mic", libs=["I2S (ESP32 Arduino core)"],
  globs=["#include <driver/i2s.h>"],
  setup=["// i2s_driver_install + i2s_set_pin with WS=@WS@, SD=@SD@, SCK=@SCK@; see ESP32 I2S docs"],
  read=["int32_t sample = 0; size_t bytesRead = 0;",
        "// i2s_read(I2S_NUM_0, &sample, sizeof(sample), &bytesRead, portMAX_DELAY);",
        "float rms = 0.0F;  // computed over a window of samples in the logic below"],
  fields=[("rms", "amplitude")],
  calibration="Set the correct I2S word alignment (24-bit in 32-bit frames) and verify DC offset removal.")

# --- derived helper ---------------------------------------------------------
def board(key: str) -> dict:
    if key not in BOARDS:
        raise KeyError(f"Unknown board {key}")
    return BOARDS[key]


def get_part(key: str) -> dict:
    if key not in PARTS:
        raise KeyError(f"Unknown part {key}")
    return deepcopy(PARTS[key])


def assign_pins(board_key: str, part_keys: list[str], overrides: dict | None = None) -> dict:
    """Deterministically assign GPIOs for a project's parts.

    Shared buses (I2C/SPI/UART) intentionally reuse pins; unique CS lines and
    single-wire signals are drawn from the board's safe pools.  Explicit
    overrides from a project spec always win.
    """
    b = board(board_key)
    overrides = overrides or {}
    assigned: dict[str, dict[str, str]] = {}
    i2c = dict(b["i2c"])
    spi = dict(b["spi"])
    uart = dict(b["uart"])

    # Pre-pass: reserve every bus pin the project will need so that a
    # single-wire signal never lands on an I2C/SPI/UART line.
    interfaces = [get_part(k)["iface"] for k in part_keys]
    bus_reserved: set[str] = set()
    if any(i == "i2c" for i in interfaces):
        bus_reserved |= {str(i2c["SDA"]), str(i2c["SCL"])}
    n_spi = sum(1 for i in interfaces if i == "spi")
    if n_spi:
        bus_reserved |= {str(v) for v in spi.values()}
        bus_reserved |= {str(b["cs_pool"][j % len(b["cs_pool"])]) for j in range(n_spi)}
    if any(i in ("uart", "i2s", "camera") for i in interfaces):
        bus_reserved |= {str(uart["RX"]), str(uart["TX"])}

    used = set(bus_reserved)
    cs_index = 0
    dig_index = ana_index = pwm_index = 0

    def take(pool, idx):
        while idx < len(pool):
            pin = str(pool[idx])
            idx += 1
            if pin not in used:
                return pin, idx
        return None, idx

    for key in part_keys:
        p = get_part(key)
        roles: dict[str, str] = {}
        for role, kind in p["signals"]:
            if kind == "analog_in":
                pin, ana_index = take(b["analog_pool"], ana_index)
                if pin is None:
                    pin = "ADC_EXTERNAL"  # boards without ADC (RPi) -> explicit external ADC note
            elif kind == "pwm_out":
                pin, pwm_index = take(b["pwm_pool"], pwm_index)
            elif kind == "spi_cs":
                pin = str(b["cs_pool"][cs_index % len(b["cs_pool"])])
                cs_index += 1
            elif kind == "uart_rx":
                pin = str(uart["RX"])
            elif kind == "uart_tx":
                pin = str(uart["TX"])
            else:
                pin, dig_index = take(b["digital_pool"], dig_index)
                if pin is None:
                    pin, pwm_index = take(b["pwm_pool"], pwm_index)
            roles[role] = str(pin)
            if pin and pin != "ADC_EXTERNAL" and kind not in ("uart_rx", "uart_tx", "spi_cs"):
                used.add(str(pin))
        if p["iface"] == "i2c":
            roles["SDA"] = str(i2c["SDA"])
            roles["SCL"] = str(i2c["SCL"])
        if p["iface"] == "spi":
            roles.update({k: str(v) for k, v in spi.items()})
        if p["iface"] == "i2s":
            roles["BUS"] = "I2S0"
        if p["iface"] == "camera":
            roles["BUS"] = "CAMERA"
        if key in overrides:
            roles.update({k: str(v) for k, v in overrides[key].items()})
        assigned[key] = roles
    return assigned


# Documentation corpus for the research / innovation tools.  Only real,
# stable documentation URLs (no invented papers or citations).
REFERENCES = [
    {"id": "REF-ESP32", "title": "Espressif ESP32 Technical Reference & Getting Started",
     "url": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/",
     "topics": ["esp32", "gpio", "adc", "wifi", "firmware"]},
    {"id": "REF-ESPIDF-ADC", "title": "ESP-IDF ADC calibration and ADC2/Wi-Fi limitation",
     "url": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/peripherals/adc.html",
     "topics": ["adc", "esp32", "wifi", "level"]},
    {"id": "REF-ARDUINO-LANG", "title": "Arduino Language Reference",
     "url": "https://www.arduino.cc/reference/en/", "topics": ["arduino", "firmware", "gpio"]},
    {"id": "REF-WIRE", "title": "Arduino Wire (I2C) library reference",
     "url": "https://www.arduino.cc/reference/en/language/functions/communication/wire/",
     "topics": ["i2c", "bus", "pull-up"]},
    {"id": "REF-I2C-SPEC", "title": "NXP I2C-bus specification (UM10204)",
     "url": "https://www.nxp.com/docs/en/user-guide/UM10204.pdf",
     "topics": ["i2c", "pull-up", "bus", "address"]},
    {"id": "REF-MQTT", "title": "MQTT Version 5.0 specification (OASIS)",
     "url": "https://docs.oasis-open.org/mqtt/mqtt/v5.0/mqtt-v5.0.html",
     "topics": ["mqtt", "telemetry", "qos", "broker"]},
    {"id": "REF-MOSQUITTO", "title": "Eclipse Mosquitto MQTT broker documentation",
     "url": "https://mosquitto.org/documentation/", "topics": ["mqtt", "broker", "tls"]},
    {"id": "REF-DS18B20", "title": "Analog Devices DS18B20 datasheet",
     "url": "https://www.analog.com/en/products/ds18b20.html", "topics": ["temperature", "onewire", "sensor"]},
    {"id": "REF-BME280", "title": "Bosch BME280 datasheet",
     "url": "https://www.bosch-sensortec.com/media/boschsensortec/downloads/datasheets/bst-bme280-ds002.pdf",
     "topics": ["humidity", "pressure", "temperature", "i2c"]},
    {"id": "REF-SCD30", "title": "Sensirion SCD30 NDIR CO2 sensor documentation",
     "url": "https://sensirion.com/products/catalog/SCD30/", "topics": ["co2", "air quality", "ndir"]},
    {"id": "REF-INA219", "title": "Texas Instruments INA219 current/voltage monitor datasheet",
     "url": "https://www.ti.com/product/INA219", "topics": ["current", "energy", "shunt"]},
    {"id": "REF-HCSR04", "title": "HC-SR04 ultrasonic module guide (SparkFun)",
     "url": "https://www.sparkfun.com/products/15569", "topics": ["distance", "ultrasonic", "level"]},
    {"id": "REF-LEVELSHIFT", "title": "Adafruit TXB0108 / BSS138 level shifting guide",
     "url": "https://learn.adafruit.com/adafruit-txb0108-logic-level-shifter",
     "topics": ["level shifter", "3.3v", "5v", "gpio"]},
    {"id": "REF-NEOPIXEL", "title": "Adafruit NeoPixel Überguide",
     "url": "https://learn.adafruit.com/adafruit-neopixel-uberguide",
     "topics": ["ws2812b", "led", "power", "level shifter"]},
    {"id": "REF-ESPNOW", "title": "Espressif ESP-NOW documentation",
     "url": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/network/esp_now.html",
     "topics": ["esp-now", "low power", "wireless"]},
    {"id": "REF-DEEPSLEEP", "title": "ESP-IDF Sleep Modes / deep sleep current",
     "url": "https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-reference/system/sleep_modes.html",
     "topics": ["deep sleep", "battery", "low power"]},
    {"id": "REF-LORA", "title": "Semtech SX1276/77/78/79 datasheet and LoRa overview",
     "url": "https://www.semtech.com/products/wireless-rf/lora-connect/sx1276",
     "topics": ["lora", "lorawan", "range", "radio"]},
    {"id": "REF-THINGSPEAK", "title": "MathWorks ThingSpeak IoT documentation",
     "url": "https://thingspeak.com/docs", "topics": ["cloud", "dashboard", "mqtt", "http"]},
    {"id": "REF-HOMEASSISTANT", "title": "Home Assistant MQTT integration documentation",
     "url": "https://www.home-assistant.io/integrations/mqtt/", "topics": ["mqtt", "home automation", "discovery"]},
    {"id": "REF-OWASP-IOT", "title": "OWASP Internet of Things Top 10 (project reference)",
     "url": "https://owasp.org/www-project-internet-of-things/",
     "topics": ["security", "iot", "hardening", "credentials"]},
    {"id": "REF-NIST-IR8425", "title": "NIST IR 8425: Consumer IoT cybersecurity criteria",
     "url": "https://csrc.nist.gov/pubs/ir/8425/final", "topics": ["security", "iot", "credentials", "update"]},
    {"id": "REF-WHO-AQI", "title": "WHO global air quality guidelines (PM2.5 context)",
     "url": "https://www.who.int/news/item/22-09-2021-new-who-global-air-quality-guidelines",
     "topics": ["air quality", "pm2.5", "health", "limits"]},
    {"id": "REF-RPI-GPIO", "title": "Raspberry Pi GPIO documentation",
     "url": "https://www.raspberrypi.com/documentation/computers/os.html#gpio-and-the-40-pin-header",
     "topics": ["raspberry pi", "gpio", "3.3v"]},
    {"id": "REF-ARDUINO-JSON", "title": "ArduinoJson library documentation",
     "url": "https://arduinojson.org/v7/api/", "topics": ["json", "firmware", "serialization"]},
    {"id": "REF-TINYGS", "title": "TinyGSM library documentation",
     "url": "https://tinygs.com/", "topics": ["cellular", "gsm", "lora", "modem"]},
    {"id": "REF-SDS011", "title": "Sensor.Community SDS011 dust sensor notes",
     "url": "https://www.sensor.community/en/sensors/dust-sensor-sds011/",
     "topics": ["pm2.5", "air quality", "uart"]},
    {"id": "REF-PLATFORMIO", "title": "PlatformIO ESP32 platform documentation",
     "url": "https://docs.platformio.org/en/latest/platforms/espressif32.html",
     "topics": ["toolchain", "build", "ci", "esp32"]},
    {"id": "REF-PCB-ESP32", "title": "Espressif ESP32 hardware design guidelines",
     "url": "https://www.espressif.com/sites/default/files/documentation/esp32_hardware_design_guidelines_en.pdf",
     "topics": ["pcb", "power", "strapping pins", "esp32"]},
]
