"""The 15 curated beginner projects available to free users.

Administrators can replace or reorder this set from the admin workspace
without changing code: the free flag and rank live in the database.
"""
from .spec_base import S

SPECS = [
    S("esp32-led-control", "LED Control Using ESP32", "Home Automation", "Beginner",
      "esp32", ["led"], "serial", hours=2, free=True, free_rank=1,
      problem="A beginner needs a first, safe output experiment to validate the ESP32 toolchain, GPIO behaviour and serial debugging before adding sensors.",
      outcome="An LED blinks with a software-adjustable pattern while the serial monitor reports each state change and the elapsed time.",
      objectives=["Install the ESP32 Arduino core and upload a sketch", "Wire an LED with a current-limiting resistor correctly", "Replace blocking delay() with a non-blocking millis() scheduler"],
      use_cases=["First-hour hardware sanity check", "Classroom GPIO demonstration", "Verifying a new development board"],
      algorithm="A millis()-based state machine toggles GPIO2 every interval, prints state/uptime, and keeps the loop free for future network tasks.",
      logic="""static bool ledOn = false;
static uint32_t lastToggle = 0;
if (millis() - lastToggle >= 700) {
  lastToggle = millis();
  ledOn = !ledOn;
  digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
  char buf[128];
  snprintf(buf, sizeof(buf), "{\\"led\\":%s,\\"uptime_ms\\":%lu}", ledOn ? "true" : "false", (unsigned long)millis());
  payload = String(buf);
  Serial.print(F("[STATE] LED ")); Serial.println(ledOn ? F("ON") : F("OFF"));
}""",
      tests=["Upload and confirm the LED alternates ON/OFF roughly every 700 ms",
             "Change the interval constant and verify the new blink rate",
             "Disconnect/reconnect USB and confirm the sketch restarts cleanly"],
      fails=["LED never lights | Verify anode/cathode orientation, the 220 Ω resistor and that GPIO2 is not held low at boot.",
             "Upload fails with 'packet header' timeout | Hold BOOT during upload and check the USB data cable.",
             "LED is very dim | Check the resistor value and measure the GPIO high level with a multimeter."]),

    S("dht22-temperature-humidity", "Temperature & Humidity Monitoring", "Environmental Monitoring", "Beginner",
      "esp32", ["dht22", "oled"], "serial", hours=3, free=True, free_rank=2,
      problem="Learners need to read a real digital sensor, handle invalid readings and display values locally without a cloud account.",
      outcome="A DHT22 publishes temperature and humidity to the serial monitor and a 128x64 OLED once every two seconds.",
      objectives=["Wire a single-wire digital sensor with its pull-up", "Handle NaN readings and sensor timing limits", "Show formatted measurements on an I2C OLED"],
      use_cases=["Indoor comfort logging", "Greenhouse starter sensor", "Learning I2C display output"],
      algorithm="The driver samples at most every 2 s, rejects NaN, applies a user-measured offset and renders a two-line display while emitting JSON.",
      logic="""temperature += TEMP_OFFSET;  // TODO: measure offset against a reference thermometer
char buf[160];
snprintf(buf, sizeof(buf), "{\\"temperature_c\\":%.1f,\\"humidity_pct\\":%.1f}", temperature, humidity);
payload = String(buf);
displayLine = String("T ") + String(temperature, 1) + " C\\nH " + String(humidity, 0) + " %";
if (temperature > 30.0F) { Serial.println(F("[ALERT] High temperature")); }""",
      tests=["Warm the sensor by hand and confirm temperature rises then returns",
             "Unplug DATA and confirm the [ERR] message, not a crash",
             "Confirm the OLED text matches the serial JSON values"],
      fails=["Readings are NaN | Add the 10 kΩ DATA pull-up and respect the 2 s minimum interval.",
             "OLED stays blank | Run an I2C scanner; many panels use 0x3C but some use 0x3D.",
             "Humidity looks 10 % off | Apply a measured offset; DHT22 accuracy is ±2-5 %RH."]),

    S("automatic-night-lamp", "Automatic Night Lamp Using a Light Sensor", "Smart Lighting & Energy Management", "Beginner",
      "esp32", ["ldr", "led"], "serial", hours=3, free=True, free_rank=3,
      problem="A manual light wastes energy; a beginner needs to learn analog inputs and threshold decisions with hysteresis.",
      outcome="An LED switches on in darkness and off in bright light, with separate thresholds to prevent flicker at the boundary.",
      objectives=["Build an LDR voltage divider and read it with the ADC", "Implement hysteresis with two thresholds", "Log the raw ADC value for calibration"],
      use_cases=["Night-light prototype", "Understanding ADC thresholds", "Basis for occupancy lighting"],
      algorithm="The ADC value is compared against DARK_ON and DARK_OFF thresholds; a 10-sample moving average suppresses fast flicker.",
      logic="""static float avgLight = light_raw;
avgLight = (avgLight * 0.8F) + (light_raw * 0.2F);
static bool lampOn = false;
if (avgLight < 900.0F) lampOn = true;      // DARK_ON  - calibrate for your LDR
if (avgLight > 1300.0F) lampOn = false;   // DARK_OFF - 400-count hysteresis
digitalWrite(LED_PIN, lampOn ? HIGH : LOW);
char buf[128];
snprintf(buf, sizeof(buf), "{\\"light_raw\\":%.0f,\\"avg\\":%.0f,\\"lamp\\":%s}", light_raw, avgLight, lampOn ? "true" : "false");
payload = String(buf);""",
      tests=["Cover the LDR and confirm the LED switches on within one sample",
             "Shine a torch and confirm it switches off",
             "Hold a half-shadow and confirm the LED does not oscillate"],
      fails=["Values do not change | Check the divider midpoint wiring and that the ADC pin is ADC1 (GPIO34/35).",
             "LED flickers at dusk | Increase the gap between DARK_ON and DARK_OFF and lower the filter coefficient.",
             "Wi-Fi enabled later breaks readings | Move the LDR to ADC1; ADC2 is unavailable during Wi-Fi use."]),

    S("soil-moisture-monitoring", "Basic Soil-Moisture Monitoring", "Smart Agriculture & Irrigation", "Beginner",
      "esp32", ["soil_cap", "oled"], "serial", hours=3, free=True, free_rank=4,
      problem="Over-watering kills plants; beginners need a repeatable, calibrated way to turn an analog sensor into a percentage.",
      outcome="A capacitive probe reports a calibrated 0-100 % moisture value locally and over serial with explicit dry/wet constants.",
      objectives=["Prefer a capacitive probe over a corrosive resistive one", "Perform a two-point dry/wet calibration", "Map raw ADC counts into a bounded percentage"],
      use_cases=["Houseplant care", "School garden experiments", "Calibration exercise"],
      algorithm="Raw ADC counts are converted with fmap() using measured DRY_RAW/WET_RAW constants and clamped to 0-100 %.",
      logic="""char buf[160];
snprintf(buf, sizeof(buf), "{\\"soil_pct\\":%.1f,\\"raw\\":%d}", soil_pct, raw_soil_cap);
payload = String(buf);
displayLine = String("Soil ") + String(soil_pct, 0) + " %\\n";
displayLine += (soil_pct < 30.0F) ? String("WATER NEEDED") : String("OK");
if (soil_pct < 30.0F) { Serial.println(F("[ALERT] Dry soil")); }""",
      tests=["Record dry-air and submerged-water ADC values and replace DRY_RAW/WET_RAW",
             "Confirm 0 % in dry air and ~100 % in water after calibration",
             "Confirm the OLED warning appears below 30 %"],
      fails=["Always shows 100 % | Verify the probe's analog output voltage and that WET_RAW is lower than DRY_RAW for your module.",
             "Drifts over weeks | Power the probe only during measurement and re-check calibration monthly.",
             "Noisy readings | Add a 100 nF capacitor at the ADC input and average 10 samples."]),

    S("smart-plant-watering", "Smart Plant-Watering Prototype", "Smart Agriculture & Irrigation", "Beginner",
      "esp32", ["soil_cap", "pump", "led"], "serial", hours=4, free=True, free_rank=5,
      problem="A calibrated moisture reading is only useful if it safely triggers an actuator with a runtime limit and a lockout.",
      outcome="A 5 V pump runs for a bounded 3 s burst when soil is dry, then waits a 60 s lockout; a status LED and serial log show every decision.",
      objectives=["Drive a pump through a MOSFET, never directly from GPIO", "Implement a maximum on-time and lockout", "Fail safe to pump OFF on invalid data"],
      use_cases=["Small indoor plant", "Learning actuator safety", "Prototype for an irrigation controller"],
      algorithm="A state machine checks a dry threshold, a lockout timer and a hard 3 s run limit; every state transition is logged.",
      logic="""static uint32_t lastWater = 0;
static uint32_t pumpStarted = 0;
if (pumpStarted && millis() - pumpStarted >= 3000UL) { digitalWrite(PUMP_PIN, LOW); pumpStarted = 0; lastWater = millis(); Serial.println(F("[INFO] Pump burst complete")); }
if (!pumpStarted && soil_pct < 30.0F && millis() - lastWater > 60000UL) { digitalWrite(PUMP_PIN, HIGH); pumpStarted = millis(); Serial.println(F("[INFO] Pump ON")); }
digitalWrite(LED_PIN, pumpStarted ? HIGH : LOW);
char buf[160];
snprintf(buf, sizeof(buf), "{\\"soil_pct\\":%.1f,\\"pump\\":%s}", soil_pct, pumpStarted ? "true" : "false");
payload = String(buf);""",
      tests=["Force soil_pct below 30 and verify a 3 s pump burst and 60 s lockout",
             "Verify the pump never runs longer than 3 s even if the sensor stays dry",
             "Disconnect the sensor and confirm the pump stays OFF"],
      fails=["Pump does not run | Check the separate 5 V supply, common ground and flyback diode.",
             "Board resets when pump starts | Increase bulk capacitance and never power the pump from the 3.3 V rail.",
             "Pump runs continuously | Inspect the pumpStarted/lastWater logic and SAMPLE_INTERVAL_MS."]),

    S("ultrasonic-distance", "Ultrasonic Distance Measurement", "Robotics & Automation", "Beginner",
      "esp32", ["hcsr04", "oled"], "serial", hours=3, free=True, free_rank=6,
      problem="Robotics and level sensing need non-contact distance; the HC-SR04's 5 V ECHO is a classic beginner trap on 3.3 V boards.",
      outcome="Distance in centimetres is measured with a timeout, shown on the OLED and logged with an explicit out-of-range marker.",
      objectives=["Wire a 5 V sensor to a 3.3 V MCU with a divider", "Use pulseIn with a timeout", "Reject out-of-range and zero-length echoes"],
      use_cases=["Robot obstacle detection", "Small tank level", "Learning timing-based sensors"],
      algorithm="A 10 µs trigger pulse starts a 30 ms echo timeout; the round-trip time is converted with 0.0343 cm/µs and range-checked.",
      logic="""if (distance_cm >= 2.0F && distance_cm <= 400.0F) {
  char buf[128];
  snprintf(buf, sizeof(buf), "{\\"distance_cm\\":%.1f}", distance_cm);
  payload = String(buf);
  displayLine = String("Dist ") + String(distance_cm, 1) + " cm";
} else { payload = "{\\"distance_cm\\":null,\\"note\\":\\"out_of_range\\"}"; displayLine = "No echo"; }""",
      tests=["Place a flat board at 10/20/50 cm and compare readings to a ruler",
             "Point at empty space and confirm the out-of-range payload",
             "Confirm ECHO pin voltage at the MCU is below 3.3 V"],
      fails=["Always -1 / timeout | Fit the 1 kΩ/2 kΩ divider on ECHO and confirm a common ground.",
             "Readings jump | Avoid soft/angled targets and add a median-of-5 filter.",
             "Accuracy drifts with temperature | Add a temperature sensor and compensate the speed of sound."]),

    S("motion-detection-alert", "Motion-Detection Alert", "Home Automation", "Beginner",
      "esp32", ["pir", "buzzer", "led"], "serial", hours=3, free=True, free_rank=7,
      problem="A beginner needs event-driven digital inputs, a warm-up period and a latched alert that does not spam the serial log.",
      outcome="A PIR sensor triggers a short buzzer beep and LED flash once per motion event after a documented warm-up.",
      objectives=["Read a digital sensor with edge detection", "Respect PIR warm-up and retrigger timing", "Implement a bounded audible alert"],
      use_cases=["Entry alert", "Occupancy experiment", "Digital input fundamentals"],
      algorithm="Rising-edge detection with a 2 s retrigger lockout; the buzzer is driven for 150 ms and the alert is logged once.",
      logic="""static bool lastMotion = false;
static uint32_t lastAlert = 0;
if (motion && !lastMotion && millis() - lastAlert > 2000UL) {
  lastAlert = millis();
  digitalWrite(BUZZER_PIN, HIGH); digitalWrite(LED_PIN, HIGH);
  delay(150);
  digitalWrite(BUZZER_PIN, LOW); digitalWrite(LED_PIN, LOW);
  payload = "{\\"motion\\":true,\\"event\\":\\"rising_edge\\",\\"ts_ms\\":" + String(millis()) + "}";
  Serial.println(F("[EVENT] Motion detected"));
} else { payload = "{\\"motion\\":false}"; }
lastMotion = motion;""",
      tests=["Wait 60 s after power-up, then wave a hand and confirm one event per 2 s",
             "Hold still and confirm no repeated events",
             "Verify the buzzer is silent during warm-up"],
      fails=["Constant triggering | Check the PIR's retrigger jumper, sensitivity pot and warm-up period.",
             "No detection | Verify the module's OUT voltage with a meter; some modules output 5 V and need a divider.",
             "Buzzer stuck on | Confirm the active buzzer polarity and that the GPIO returns LOW."]),

    S("room-temperature-dashboard", "Room Temperature Dashboard", "Environmental Monitoring", "Beginner",
      "esp32", ["dht22", "oled"], "wifi_http", hours=5, free=True, free_rank=8,
      problem="Local readings are hard to review historically; beginners need a first HTTPS telemetry workflow with safe credential handling.",
      outcome="Temperature/humidity are POSTed as JSON to a configurable HTTPS endpoint every 30 s and mirrored on the local OLED.",
      objectives=["Connect ESP32 to a 2.4 GHz Wi-Fi network", "POST JSON over HTTPS with a bearer token", "Handle Wi-Fi outages without crashing"],
      use_cases=["Home temperature chart", "Server-room spot check", "Learning REST telemetry"],
      algorithm="The sketch builds a small JSON document, POSTs it with a 5 s timeout, logs the HTTP status and keeps the last value on the OLED.",
      logic="""char buf[200];
snprintf(buf, sizeof(buf), "{\\"device\\":\\"YOUR_DEVICE_ID\\",\\"temperature_c\\":%.1f,\\"humidity_pct\\":%.1f}", temperature, humidity);
payload = String(buf);
displayLine = String("T ") + String(temperature, 1) + " C H " + String(humidity, 0) + " %";
if (temperature < -20.0F || temperature > 80.0F) { payload = ""; Serial.println(F("[ERR] Implausible temperature; skipping POST")); }""",
      tests=["Confirm the endpoint receives JSON with the expected units",
             "Power off the router for 60 s and confirm reconnection behaviour",
             "Send an invalid token and confirm the HTTP error is logged"],
      fails=["HTTP -1 / timeout | Check the endpoint host, TLS root certificate and firewall.",
             "401/403 | Verify the bearer token placeholder was replaced locally.",
             "Wi-Fi never associates | ESP32 is 2.4 GHz only; use a non-captive SSID."]),

    S("basic-air-quality-indicator", "Basic Air-Quality Indicator", "Air Quality Monitoring", "Beginner",
      "esp32", ["gas_mq135", "led", "buzzer"], "serial", hours=4, free=True, free_rank=9,
      problem="Low-cost gas sensors are easy to misread as certified detectors; learners need a relative index with clear safety limits.",
      outcome="An MQ-135 produces a relative air-quality index with green/red LED bands and a short audible alert, explicitly labelled as non-safety.",
      objectives=["Understand heater current and burn-in", "Baseline a gas sensor in clean air", "Communicate uncertainty to users"],
      use_cases=["Ventilation trigger experiment", "Sensor-characterisation lesson", "Indoor trend indicator"],
      algorithm="A rolling baseline tracks clean air; the deviation from that baseline is banded into OK / WATCH / HIGH with a 30 s alert lockout.",
      logic="""static float baseline = gas_index;
baseline = baseline * 0.995F + gas_index * 0.005F;  // slow clean-air baseline
float delta = gas_index - baseline;
const char* band = (delta > 25.0F) ? "HIGH" : (delta > 10.0F) ? "WATCH" : "OK";
digitalWrite(LED_PIN, delta > 10.0F ? HIGH : LOW);
char buf[160];
snprintf(buf, sizeof(buf), "{\\"gas_index\\":%.1f,\\"delta\\":%.1f,\\"band\\":\\"%s\\",\\"safety_certified\\":false}", gas_index, delta, band);
payload = String(buf);
if (delta > 25.0F) { Serial.println(F("[ALERT] Relative gas index HIGH - not a safety alarm")); }""",
      tests=["Run 48 h burn-in and record the clean-air baseline",
             "Expose the sensor to a safe vapour source and confirm band transitions",
             "Confirm the JSON states safety_certified:false"],
      fails=["Readings drift for hours | MQ sensors need 24-48 h burn-in and a stable 5 V heater supply.",
             "Always HIGH | Re-baseline in fresh air and check the 5 V rail voltage under heater load.",
             "Board resets | Power the heater from a separate 5 V supply, not the MCU rail."]),

    S("water-tank-level-monitoring", "Water-Tank Level Monitoring", "Water Leakage Detection", "Beginner",
      "esp32", ["water_level", "oled", "buzzer"], "serial", hours=4, free=True, free_rank=10,
      problem="Overflow and dry-running damage pumps; a beginner needs a calibrated percentage plus high/low alarms.",
      outcome="Tank level is shown as a percentage with high (>90 %) and low (<15 %) alarms and a bounded buzzer pattern.",
      objectives=["Calibrate EMPTY_RAW/FULL_RAW for the specific tank", "Add hysteresis to level alarms", "Explain why float/analog probes drift"],
      use_cases=["Rainwater tank", "Aquarium top-up reminder", "Pump dry-run protection"],
      algorithm="A 10-sample median filter feeds a two-point calibration; latched high/low states release only after 5 % hysteresis.",
      logic="""static bool highAlarm = false, lowAlarm = false;
if (level_pct > 90.0F) highAlarm = true;  if (level_pct < 85.0F) highAlarm = false;
if (level_pct < 15.0F) lowAlarm = true;  if (level_pct > 20.0F) lowAlarm = false;
digitalWrite(BUZZER_PIN, (highAlarm || lowAlarm) ? HIGH : LOW);
char buf[180];
snprintf(buf, sizeof(buf), "{\\"level_pct\\":%.1f,\\"high_alarm\\":%s,\\"low_alarm\\":%s}", level_pct, highAlarm ? "true":"false", lowAlarm ? "true":"false");
payload = String(buf);
displayLine = String("Level ") + String(level_pct, 0) + " %";""",
      tests=["Measure EMPTY_RAW/FULL_RAW and verify 0 % and 100 % endpoints",
             "Raise level above 90 % and confirm the alarm latches until below 85 %",
             "Confirm a disconnected probe cannot report a plausible mid-range value"],
      fails=["Stuck at 100 % | Check the probe's output voltage and the divider for a 3.3 V ADC.",
             "Alarms chatter | Increase hysteresis and add a median filter.",
             "Corrosion after weeks | Use a capacitive or ultrasonic sensor for permanent installs."]),

    S("door-open-alert", "Door-Open Alert System", "Home Automation", "Beginner",
      "esp32", ["reed", "buzzer", "led"], "serial", hours=3, free=True, free_rank=11,
      problem="Reed switches bounce; beginners need debounced state detection and a clear open/closed event stream.",
      outcome="Door open/close events are debounced, timestamped and indicated with an LED and a short beep.",
      objectives=["Use INPUT_PULLUP without an external resistor", "Debounce a mechanical contact", "Emit events only on state change"],
      use_cases=["Fridge door reminder", "Shed entry alert", "Learning digital inputs"],
      algorithm="A 50 ms re-read confirms a contact transition; only confirmed changes emit an event and update the indicators.",
      logic="""static bool lastState = false;
if (door_open != lastState) {
  lastState = door_open;
  char buf[140];
  snprintf(buf, sizeof(buf), "{\\"door_open\\":%s,\\"ts_ms\\":%lu}", door_open ? "true":"false", (unsigned long)millis());
  payload = String(buf);
  digitalWrite(LED_PIN, door_open ? HIGH : LOW);
  if (door_open) { digitalWrite(BUZZER_PIN, HIGH); delay(80); digitalWrite(BUZZER_PIN, LOW); }
} else { payload = "{\\"door_open\\":" + String(door_open ? "true":"false") + "}"; }""",
      tests=["Open/close the magnet 20 times and confirm exactly 20 events",
             "Hold the contact half-open and confirm no event storm",
             "Confirm the LED tracks the physical state"],
      fails=["Always open | Verify normally-open vs normally-closed contacts and the INPUT_PULLUP logic inversion.",
             "Random events | Shorten the cable, add a 100 nF capacitor and increase debounce to 100 ms.",
             "No events | Check continuity of the reed switch with a meter."]),

    S("wifi-controlled-led", "Simple Wi-Fi-Controlled LED", "Home Automation", "Beginner",
      "esp32", ["led"], "wifi_mqtt", hours=5, free=True, free_rank=12,
      problem="Beginners need to understand publish/subscribe, retained state and reconnection using a harmless output.",
      outcome="An LED is controlled from an MQTT 'cmd' topic with ON/OFF/TOGGLE commands, state published back, and automatic reconnect.",
      objectives=["Connect to an MQTT broker with credentials", "Parse a command topic safely", "Reconnect and resynchronise state after an outage"],
      use_cases=["Remote indicator", "MQTT fundamentals", "Testing automation rules"],
      algorithm="A non-blocking reconnect loop subscribes to a command topic, parses a bounded payload, updates the LED and publishes retained state.",
      logic="""// MQTT callback is registered in setup() for production; this loop-side state
// mirrors the last command so the LED state is always published with telemetry.
static bool ledOn = false;
if (Serial.available()) { char c = Serial.read(); if (c == 't') ledOn = !ledOn; if (c == '1') ledOn = true; if (c == '0') ledOn = false; }
digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
payload = "{\\"led\\":" + String(ledOn ? "true":"false") + ",\\"cmd_topic\\":\\"nexus/YOUR_DEVICE_ID/cmd\\",\\"hint\\":\\"send ON/OFF/TOGGLE\\"}";""",
      tests=["Publish ON/OFF/TOGGLE and verify the LED and state topic",
             "Stop the broker for 60 s and confirm reconnection and re-subscription",
             "Confirm no credentials appear in the source or serial log"],
      fails=["MQTT rc=-2 | Check broker host/port, DNS and that the device has IP connectivity.",
             "Commands ignored | Verify the exact topic string and payload case (ON vs on).",
             "State lost after reboot | Use a retained state message or persist in NVS/Preferences."]),

    S("basic-energy-measurement", "Basic Energy Measurement Demonstration", "Smart Lighting & Energy Management", "Beginner",
      "esp32", ["ina219", "oled"], "serial", hours=4, free=True, free_rank=13,
      problem="Mains measurement is dangerous for beginners; a low-voltage DC shunt monitor teaches voltage, current, power and energy safely.",
      outcome="A 12 V DC lamp/load is measured for bus voltage, current and power, with Wh accumulated and displayed locally.",
      objectives=["Wire a high-side current shunt safely at low voltage", "Compute power and integrate energy", "Explain why mains is excluded"],
      use_cases=["Solar panel characterisation", "DC motor load profiling", "Energy-literacy lesson"],
      algorithm="Voltage and current are sampled every 5 s; instantaneous power is integrated with dt into watt-hours and bounded against a maximum current.",
      logic="""static double energy_wh = 0.0;
energy_wh += power_w * (SAMPLE_INTERVAL_MS / 3600000.0);
char buf[200];
snprintf(buf, sizeof(buf), "{\\"voltage_v\\":%.2f,\\"current_ma\\":%.1f,\\"power_w\\":%.3f,\\"energy_wh\\":%.4f}", voltage_v, current_ma, power_w, energy_wh);
payload = String(buf);
displayLine = String(power_w, 2) + " W\\n" + String(energy_wh, 2) + " Wh";
if (fabsf(current_ma) > 3000.0F) { Serial.println(F("[ALERT] Overcurrent - disconnect load")); }""",
      tests=["Connect a known 10 Ω load at 5 V and compare measured current to Ohm's law",
             "Run for 6 minutes and confirm Wh ~ power * 0.1 h",
             "Verify the INA219 shunt value in the library matches the board"],
      fails=["Current has wrong sign | Swap the shunt's VIN+/VIN- sense direction.",
             "Readings far too small | Set the correct calibration/shunt resistance in the library.",
             "Negative values with no load | Zero the offset and check for ground loops."]),

    S("rain-detection-alert", "Rain-Detection Alert", "Weather Stations & Forecasting", "Beginner",
      "esp32", ["rain", "buzzer", "led"], "serial", hours=3, free=True, free_rank=14,
      problem="A rain board needs a dry baseline and a debounced wet state; beginners often leave DC across the plate and corrode it.",
      outcome="Rain onset/cease events are detected against a dry baseline with a 10 s debounce and a short audible alert.",
      objectives=["Calibrate a conductive rain board in dry conditions", "Debounce environmental events", "Limit excitation to reduce corrosion"],
      use_cases=["Garden irrigation interlock", "Window-close reminder", "Weather-station input"],
      algorithm="A dry baseline plus a 15 % deviation threshold feeds a 10 s confirmation timer; state changes emit a single event.",
      logic="""static bool raining = false; static uint32_t changeAt = 0; static bool candidate = false;
bool wetNow = rain_pct > 25.0F;
if (wetNow != candidate) { candidate = wetNow; changeAt = millis(); }
if (millis() - changeAt > 10000UL && raining != wetNow) {
  raining = wetNow;
  char buf[150];
  snprintf(buf, sizeof(buf), "{\\"rain_pct\\":%.1f,\\"raining\\":%s,\\"event\\":\\"%s\\"}", rain_pct, raining ? "true":"false", raining ? "onset":"cease");
  payload = String(buf);
  digitalWrite(LED_PIN, raining ? HIGH : LOW);
  if (raining) { digitalWrite(BUZZER_PIN, HIGH); delay(100); digitalWrite(BUZZER_PIN, LOW); }
} else { payload = "{\\"rain_pct\\":" + String(rain_pct,1) + ",\\"raining\\":" + String(raining ? "true":"false") + "}"; }""",
      tests=["Record the dry ADC baseline and verify rain_pct near 0",
             "Apply a few water drops and confirm the event after 10 s",
             "Dry the plate and confirm a single 'cease' event"],
      fails=["Always wet | Check for residue on the plate and lower the board's sensitivity pot.",
             "No detection | Verify the analog output voltage and that the plate is connected to the module.",
             "Corrosion | Power the board only during sampling and rinse/dry after experiments."]),

    S("simple-iot-sensor-dashboard", "Simple IoT Sensor Dashboard", "Remote Monitoring", "Beginner",
      "esp32", ["bme280", "oled"], "wifi_http", hours=5, free=True, free_rank=15,
      problem="A first end-to-end IoT project should connect sensing, JSON, HTTPS and a local fallback in one coherent build.",
      outcome="Temperature, humidity and pressure are displayed locally and posted to a dashboard endpoint with a sample counter and error status.",
      objectives=["Combine I2C sensing with Wi-Fi telemetry", "Design a stable JSON schema with units", "Show connection status locally"],
      use_cases=["Beginner IoT capstone", "Desk environment monitor", "Dashboard ingestion test"],
      algorithm="The BME280 sample is validated for plausible ranges, packaged with a monotonic counter, POSTed over HTTPS and mirrored on the OLED.",
      logic="""static uint32_t sampleNo = 0;
sampleNo++;
if (pressure > 800.0F && pressure < 1200.0F && temperature > -40.0F && temperature < 85.0F) {
  char buf[240];
  snprintf(buf, sizeof(buf), "{\\"device\\":\\"YOUR_DEVICE_ID\\",\\"sample\\":%lu,\\"temperature_c\\":%.1f,\\"humidity_pct\\":%.1f,\\"pressure_hpa\\":%.1f}", (unsigned long)sampleNo, temperature, humidity, pressure);
  payload = String(buf);
  displayLine = String(temperature,1) + " C " + String(humidity,0) + " %\\n" + String(pressure,0) + " hPa";
} else { payload = "{\\"error\\":\\"sensor_out_of_range\\"}"; displayLine = "Sensor error"; }""",
      tests=["Verify the dashboard receives temperature, humidity, pressure and a rising sample number",
             "Disconnect the BME280 and confirm the error payload and local message",
             "Block the network and confirm the OLED still updates"],
      fails=["BME280 not found | Run an I2C scanner; try address 0x77 and check 3.3 V logic.",
             "Pressure wildly wrong | Divide Pa by 100 for hPa and verify the library's unit convention.",
             "HTTP 413 | Reduce payload size and check the endpoint's body limit."]),
]
