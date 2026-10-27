"""Pro library part A: agriculture, environment, weather, water, leakage, home."""
from .spec_base import S

SPECS = [
    S("multi-zone-irrigation-controller", "Multi-Zone Adaptive Irrigation Controller", "Smart Agriculture & Irrigation", "Advanced",
      "esp32", ["soil_cap", "rain", "dht22", "valve", "oled"], "wifi_mqtt", hours=12, advanced=True,
      problem="A single moisture threshold wastes water because it ignores rain, humidity and valve feedback across different soil types.",
      outcome="A controller irrigates only when soil is dry AND rain is absent AND humidity is low, with a bounded valve-on window and a per-cycle water budget.",
      objectives="Fuse three environmental inputs into one irrigation decision|Enforce a maximum valve runtime and a daily budget|Publish decisions with the contributing sensor values",
      use_cases="Market garden beds|Research plot watering|Water-efficient landscaping",
      algorithm="Weighted decision score from soil_pct, rain_pct and humidity; a leaky-bucket daily water budget gates the valve, and a watchdog forces it OFF.",
      logic="""float score = (30.0F - soil_pct) * 0.6F + (humidity < 60.0F ? 10.0F : 0.0F) - rain_pct * 0.3F;
static uint16_t secondsUsedToday = 0; static uint32_t valveAt = 0;
if (valveAt && millis() - valveAt >= 20000UL) { digitalWrite(VALVE_PIN, LOW); valveAt = 0; secondsUsedToday += 20; }
if (!valveAt && score > 12.0F && rain_pct < 15.0F && secondsUsedToday < 120) { digitalWrite(VALVE_PIN, HIGH); valveAt = millis(); }
char buf[256];
snprintf(buf, sizeof(buf), "{\\"soil_pct\\":%.1f,\\"rain_pct\\":%.1f,\\"humidity_pct\\":%.1f,\\"score\\":%.1f,\\"valve\\":%s,\\"seconds_today\\":%u}", soil_pct, rain_pct, humidity, score, valveAt ? "true":"false", secondsUsedToday);
payload = String(buf);
displayLine = String("Score ") + String(score,1) + "\\nValve " + String(valveAt ? "ON":"OFF");""",
      tests="Dry soil + no rain + low humidity triggers one 20 s valve cycle|Rain above 15 % blocks irrigation even with dry soil|Budget exhaustion stops all further cycles until reset",
      fails="Valve stays open | Fit the flyback diode and verify the MOSFET gate pull-down.|Score never exceeds threshold | Recalibrate DRY_RAW/WET_RAW and check rain baseline.|MQTT state disagrees with valve | Publish the actual GPIO readback, not the intended state."),

    S("greenhouse-climate-controller", "Greenhouse Climate Controller with CO₂ and Ventilation", "Smart Agriculture & Irrigation", "Advanced",
      "esp32", ["scd30", "fan", "servo", "oled"], "wifi_mqtt", hours=14, advanced=True,
      problem="Greenhouses need coordinated CO₂, temperature and ventilation control, but naive independent thresholds fight each other.",
      outcome="An ESP32 balances CO₂ enrichment requests against temperature using a vent servo and exhaust fan, with an explicit state machine.",
      objectives="Coordinate actuators with a priority-based state machine|Log CO₂ with temperature and humidity for traceability|Provide a local fail-safe vent position",
      use_cases="Small greenhouse|Vertical farm bay|Plant-growth chamber",
      algorithm="A three-state machine (IDLE/VENT/ENRICH) evaluates CO₂ and temperature with hysteresis and a minimum dwell time to avoid actuator chatter.",
      logic="""static const char* state = "IDLE"; static uint32_t entered = 0;
const char* next = (temperature > 29.0F) ? "VENT" : (co2 < 700.0F && temperature < 26.0F) ? "ENRICH" : "IDLE";
if (strcmp(next, state) && millis() - entered > 60000UL) { state = next; entered = millis(); }
bool venting = strcmp(state,"VENT") == 0;
digitalWrite(FAN_PIN, venting ? HIGH : LOW);
actuator.write(venting ? 90 : 15);
char buf[240];
snprintf(buf, sizeof(buf), "{\\"co2_ppm\\":%.0f,\\"temperature_c\\":%.1f,\\"humidity_pct\\":%.1f,\\"state\\":\\"%s\\",\\"vent_deg\\":%d}", co2, temperature, humidity, state, venting ? 90:15);
payload = String(buf);
displayLine = String(co2,0) + " ppm\\n" + String(state);""",
      tests="Raise temperature above 29 °C and confirm VENT state plus 90° vent|Lower CO₂ below 700 ppm at 24 °C and confirm ENRICH|Rapidly oscillate inputs and confirm 60 s dwell prevents flapping",
      fails="SCD30 reads 0 ppm | Check 0x61 address and allow the 7-day ASC period or force calibration.|Servo jitter | Power the servo from the external 5 V rail, not the ESP32.|Fan and vent fight | Verify the state machine priorities in the serial log."),

    S("irrigation-flow-feedback", "Closed-Loop Irrigation with Flow Feedback", "Smart Agriculture & Irrigation", "Intermediate",
      "esp32", ["soil_cap", "hall", "valve", "buzzer"], "wifi_mqtt", hours=10,
      problem="A commanded valve does not guarantee delivered water; a blocked line or empty tank can silently kill a crop.",
      outcome="The controller compares commanded dose to measured flow pulses and raises a no-flow fault while shutting the valve.",
      objectives="Count flow pulses with an interrupt|Detect no-flow and over-flow conditions|Report delivered litres alongside commanded litres",
      use_cases="Drip irrigation|Hydroponic dosing|Fertigation prototype",
      algorithm="Pulse counting over a sample window yields L/min and delivered volume; if the valve is open but flow is below 0.2 L/min for 10 s, the cycle aborts.",
      logic="""static bool fault = false; static uint32_t drySince = 0;
float litres = flow_lpm * (SAMPLE_INTERVAL_MS / 60000.0F);
bool valveOn = digitalRead(VALVE_PIN) == HIGH;
if (valveOn && flow_lpm < 0.2F) { if (!drySince) drySince = millis(); if (millis()-drySince > 10000UL) { fault = true; digitalWrite(VALVE_PIN, LOW); } }
else { drySince = 0; }
if (fault) { digitalWrite(BUZZER_PIN, HIGH); }
char buf[220];
snprintf(buf, sizeof(buf), "{\\"soil_pct\\":%.1f,\\"flow_lpm\\":%.2f,\\"litres\\":%.3f,\\"no_flow_fault\\":%s}", soil_pct, flow_lpm, litres, fault ? "true":"false");
payload = String(buf);""",
      tests="Run water through the meter and confirm litres scale with pulse count|Clamp the tube with the valve open and confirm the 10 s fault|Clear the fault via a serial 'r' command after restoring flow",
      fails="Flow always zero | Verify the YF-S201 K-factor and that the interrupt pin supports attachInterrupt.|False no-flow fault | Increase the 0.2 L/min threshold for low-flow drippers.|Pulses double counted | Add RC debouncing or use the sensor's Schmitt output."),

    S("hydroponic-nutrient-monitor", "Hydroponic pH, EC and Temperature Monitor", "Water Quality Monitoring", "Advanced",
      "esp32", ["ph", "tds", "ds18b20", "oled"], "wifi_http", hours=12, advanced=True,
      problem="Nutrient solutions drift outside the usable pH/EC range and temperature changes bias both measurements.",
      outcome="A monitoring node reports temperature-compensated pH and TDS with calibration metadata and out-of-range alerts.",
      objectives="Apply two-point pH calibration in firmware|Temperature-compensate conductivity|Expose calibration age in the telemetry",
      use_cases="Home hydroponics|Aquaponics research|Nutrient mixing bench",
      algorithm="pH uses a two-point linear fit; TDS applies a 2 %/°C compensation relative to 25 °C; both readings are tagged with a calibration timestamp.",
      logic="""float tds_comp = tds_ppm / (1.0F + 0.02F * (temperature - 25.0F));
bool phBad = (ph_value < 5.5F || ph_value > 6.5F);
bool ecBad = (tds_comp < 800.0F || tds_comp > 1600.0F);
char buf[260];
snprintf(buf, sizeof(buf), "{\\"ph\\":%.2f,\\"tds_ppm_raw\\":%.0f,\\"tds_ppm_25c\\":%.0f,\\"water_c\\":%.1f,\\"ph_out\\":%s,\\"ec_out\\":%s}", ph_value, tds_ppm, tds_comp, temperature, phBad?"true":"false", ecBad?"true":"false");
payload = String(buf);
displayLine = String("pH ") + String(ph_value,2) + "\\nEC " + String(tds_comp,0);
if (phBad || ecBad) Serial.println(F("[ALERT] Nutrient solution out of range"));""",
      tests="Calibrate with pH 4.0 and 7.0 buffers and verify both endpoints|Warm the solution 10 °C and confirm TDS compensation changes ~20 %|Verify a disconnected probe produces an out-of-range error, not a plausible value",
      fails="pH drifts daily | Replace ageing probe, add a 100 nF cap and recalibrate weekly.|TDS implausibly high | Verify the probe K-value and the 3.3 V divider on the analog board.|Ground loops between probes | Use isolated interfaces or a single-star ground."),

    S("livestock-trough-monitor", "Remote Livestock Water-Trough Monitor", "Smart Agriculture & Irrigation", "Intermediate",
      "picow", ["water_level", "ds18b20", "gsm"], "gsm", hours=12,
      problem="Remote troughs can freeze or run dry; there is often no Wi-Fi, only cellular coverage and solar power.",
      outcome="A Pico W node sends level and water temperature over cellular with a freeze warning and a daily heartbeat.",
      objectives="Use a 1-Wire temperature probe for water temperature|Send telemetry over a GSM modem|Implement a low-power duty cycle",
      use_cases="Pasture water point|Remote farm asset|Off-grid telemetry",
      algorithm="Samples are batched hourly; a freeze alert is sent immediately when water temperature drops below 2 °C; modem sleeping between transmissions.",
      logic="""static uint32_t lastSend = 0;
bool freeze = temperature < 2.0F;
if (freeze || millis() - lastSend > 3600000UL) {
  lastSend = millis();
  char buf[200];
  snprintf(buf, sizeof(buf), "{\\"level_pct\\":%.1f,\\"water_c\\":%.1f,\\"freeze_risk\\":%s,\\"heartbeat\\":true}", level_pct, temperature, freeze?"true":"false");
  payload = String(buf);
} else { payload = ""; }""",
      tests="Dip the DS18B20 in ice water and confirm an immediate freeze alert|Confirm an hourly heartbeat with no alert|Disconnect the antenna and confirm a logged failure, not a hang",
      fails="Modem resets on TX | Provide a 2 A peak supply and a 1000 µF capacitor.|No network | Verify 2G/4G band support in your country before buying.|Level stuck | Use an ultrasonic sensor if float switches foul."),

    S("forest-fire-risk-node", "Forest Fire Early-Warning Sensor Node", "Environmental Monitoring", "Advanced",
      "esp32", ["dht22", "gas_mq2", "gps", "lora"], "lora", hours=16, advanced=True,
      problem="Remote forests lack connectivity and power; early warning needs long-range radio, local risk scoring and a position fix.",
      outcome="A LoRa node broadcasts a fire-risk score derived from temperature, humidity and smoke index with GPS coordinates.",
      objectives="Fuse smoke/humidity/temperature into a transparent risk score|Use LoRa within regional duty-cycle limits|Include location and battery metadata in each packet",
      use_cases="Forest edge monitoring|Campus fire research|Remote sensing exercise",
      algorithm="A weighted score (0-100) triggers immediate transmission when above 70; otherwise a 15-minute heartbeat with a compact binary-like CSV payload.",
      logic="""float risk = constrain((temperature - 25.0F) * 2.0F + (40.0F - humidity) * 1.2F + gas_index * 0.5F, 0.0F, 100.0F);
static uint32_t lastTx = 0;
if (risk > 70.0F || millis() - lastTx > 900000UL) {
  lastTx = millis();
  char buf[160];
  snprintf(buf, sizeof(buf), "%.1f,%.1f,%.1f,%.1f,%.5f,%.5f,%s", risk, temperature, humidity, gas_index, lat, lng, risk > 70.0F ? "ALERT":"HB");
  payload = String(buf);
} else { payload = ""; }""",
      tests="Heat the sensor and confirm an immediate ALERT packet|Confirm a heartbeat within 15 min with no smoke|Verify the LoRa duty cycle stays within regional limits",
      fails="LoRa init fails | Check antenna, SPI CS/RST/DIO0 and the regional frequency constant.|GPS never fixes | Move outdoors; cold start can take several minutes.|False alarms at midday | Lower the temperature weight and add a daily baseline."),

    S("river-level-telemetry", "River-Level and Rainfall Telemetry Station", "Environmental Monitoring", "Advanced",
      "esp32", ["hcsr04", "bme280", "gsm"], "gsm", hours=16, advanced=True,
      problem="Flood watches need remote water-level and pressure trends where Wi-Fi is unavailable and enclosures are exposed.",
      outcome="A cellular station reports river distance-to-water, barometric pressure and a rate-of-rise warning.",
      objectives="Mount an ultrasonic sensor above the water line|Compute a rate-of-rise trend over 30 min|Send alerts over cellular with a daily heartbeat",
      use_cases="Creek flood watch|Bridge scour research|Small reservoir monitoring",
      algorithm="Distance is converted to stage height using a surveyed offset; a 30-minute linear slope triggers a rise alert; pressure adds weather context.",
      logic="""float stage_cm = MOUNT_HEIGHT_CM - distance_cm;
static float history[6] = {0}; static uint8_t idx = 0;
history[idx++ % 6] = stage_cm;
float slope = (history[(idx-1)%6] - history[idx%6]) / 30.0F;  // cm per minute-ish
bool rising = slope > 2.0F;
char buf[220];
snprintf(buf, sizeof(buf), "{\\"stage_cm\\":%.1f,\\"rise_rate\\":%.2f,\\"pressure_hpa\\":%.1f,\\"temperature_c\\":%.1f,\\"rising_alert\\":%s}", stage_cm, slope, pressure, temperature, rising?"true":"false");
payload = String(buf);""",
      tests="Move a target board 10 cm and confirm the stage change|Simulate a rising trend and confirm the alert|Verify the enclosure's IP rating and cable glands",
      fails="Echo lost over water | Use a waterproof JSN-SR04T or a pressure transducer.|Cellular data cost too high | Batch samples and compress the payload.|Condensation ruins readings | Add a breather membrane and conformal coating."),

    S("noise-mapping-node", "Community Noise-Mapping Logger", "Environmental Monitoring", "Intermediate",
      "uno", ["sound", "rtc", "sdcard"], "sd_local", hours=9,
      problem="Noise complaints need time-stamped evidence, but a phone app is not a calibrated instrument and drains its battery.",
      outcome="An Arduino Uno logs 1-second sound index samples with RTC timestamps to SD in CSV format for later analysis.",
      objectives="Window RMS-style sampling with a low-cost microphone|Timestamp records with a battery-backed RTC|Write a corruption-resistant CSV log",
      use_cases="Neighbourhood noise study|Classroom acoustics|Traffic noise mapping",
      algorithm="Ten analog samples per second are averaged; the RTC supplies ISO-like timestamps; each CSV row is flushed to SD with a size check.",
      logic="""char buf[160];
snprintf(buf, sizeof(buf), "%s,%d,%.1f,%s", timestamp, raw_sound, sound_index, sound_index > 70.0F ? "LOUD":"normal");
payload = String(buf);
logLine = payload;
Serial.println(payload);""",
      tests="Clap near the mic and confirm a LOUD row with a valid timestamp|Remove power mid-log and confirm earlier rows survive|Compare relative levels at 1 m and 3 m",
      fails="SD init fails | Format FAT32 and check the 3.3 V level shifter on the SD module.|RTC time resets | Replace the coin cell and set the time once.|Values always max | Lower the module gain or add a divider."),

    S("microclimate-grid", "Low-Cost Microclimate Sensor Grid", "Environmental Monitoring", "Intermediate",
      "esp32", ["sht31", "soil_cap", "ldr", "oled"], "espnow", hours=11,
      problem="A single sensor cannot capture spatial variation across a field or building; wired grids are expensive.",
      outcome="Multiple ESP-NOW leaf nodes send temperature, humidity, soil moisture and light to one receiver with a node ID.",
      objectives="Use ESP-NOW without a router|Design a compact payload with a node identifier|Detect stale nodes with a heartbeat watchdog",
      use_cases="Greenhouse zoning|Urban heat island study|Campus microclimate",
      algorithm="Each node samples on a staggered interval derived from its MAC-derived ID; the receiver rejects stale packets older than 5 minutes.",
      logic="""uint32_t nodeId = (uint32_t)(ESP.getEfuseMac() & 0xFFFF);
static uint32_t seq = 0; seq++;
char buf[220];
snprintf(buf, sizeof(buf), "{\\"node\\":%lu,\\"seq\\":%lu,\\"temp_c\\":%.1f,\\"rh\\":%.1f,\\"soil_pct\\":%.1f,\\"light_raw\\":%.0f}", (unsigned long)nodeId, (unsigned long)seq, temperature, humidity, soil_pct, light_raw);
payload = String(buf);
displayLine = String("Node ") + String(nodeId) + " " + String(temperature,1) + "C";""",
      tests="Power two nodes and confirm both IDs at the receiver|Switch one off and confirm the stale-node watchdog|Verify 30 m range in open air",
      fails="ESP-NOW send fails | Add the peer MAC correctly and use the same Wi-Fi channel.|Nodes collide | Stagger send times by nodeId modulo the interval.|SHT31 not found | Verify 0x44 vs 0x45 and the 3.3 V rail."),

    S("compact-weather-station", "Compact Weather Station with Rain and Wind", "Weather Stations & Forecasting", "Intermediate",
      "esp32", ["bme280", "rain", "hall", "ldr", "sdcard"], "wifi_mqtt", hours=14,
      problem="Weather stations need several independent sensors to share one controller without pin, bus or power conflicts.",
      outcome="A station reports temperature, humidity, pressure, rainfall state, wind-speed proxy and light to MQTT with local CSV backup.",
      objectives="Combine I2C, analog and pulse-count sensors on one board|Timestamp and buffer samples on SD|Publish a documented topic schema",
      use_cases="School weather station|Farm weather log|Roof-top climate monitor",
      algorithm="Anemometer pulses are integrated into a wind speed using a measured K-factor; climate values are sampled every 60 s and appended to CSV.",
      logic="""float wind_ms = (flow_lpm / 7.5F) * ANEMO_FACTOR;  // TODO measure with a known reference
char buf[280];
snprintf(buf, sizeof(buf), "{\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"p_hpa\\":%.1f,\\"rain_pct\\":%.1f,\\"wind_ms\\":%.2f,\\"light_raw\\":%.0f}", temperature, humidity, pressure, rain_pct, wind_ms, light_raw);
payload = String(buf);
logLine = String("WEATHER,") + payload;""",
      tests="Spin the anemometer by hand and confirm a plausible wind_ms|Compare BME280 pressure with a local METAR report|Disconnect MQTT and confirm CSV rows continue",
      fails="Wind reads zero | Verify the hall sensor pull-up and the K-factor.|Rain board stays wet | Clean the plate and recalibrate DRY_RAW.|SD write errors | Add a 100 µF cap near the SD module and use FAT32."),

    S("barometric-nowcaster", "Barometric Trend Nowcaster", "Weather Stations & Forecasting", "Intermediate",
      "esp32", ["bme280", "rtc", "sdcard", "oled"], "wifi_http", hours=10,
      problem="A single pressure reading is less useful than its rate of change over three hours for short-term forecasting.",
      outcome="A device stores hourly pressure samples, computes a 3-hour trend and displays a plain-language nowcast.",
      objectives="Persist a ring buffer of pressure samples across reboots|Compute a least-squares slope|Explain forecast uncertainty",
      use_cases="Small-craft weather aid|Hiking club station|Teaching trend analysis",
      algorithm="A 3-hour least-squares slope in hPa/h is classified as falling fast (> -1), falling, steady or rising; the result is clearly labelled a heuristic.",
      logic="""static float p[3] = {0,0,0}; static uint8_t n = 0;
p[n++ % 3] = pressure;
float slope = (n >= 3) ? (p[2] - p[0]) / 3.0F : 0.0F;
const char* nowcast = slope < -1.0F ? "FALLING_FAST" : slope < -0.3F ? "FALLING" : slope > 0.3F ? "RISING" : "STEADY";
char buf[200];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"pressure_hpa\\":%.1f,\\"slope_hpa_h\\":%.2f,\\"nowcast\\":\\"%s\\",\\"heuristic\\":true}", timestamp, pressure, slope, nowcast);
payload = String(buf);
displayLine = String(pressure,1) + " hPa\\n" + String(nowcast);""",
      tests="Feed three synthetic pressures and verify the slope calculation|Confirm FALLING_FAST classification|Verify the ring buffer survives a controlled reboot",
      fails="Slope always zero | Confirm hourly sampling actually advances the ring buffer.|RTC drift | Sync periodically with NTP or GPS.|False forecast claims | Keep the heuristic flag and disclaimer in the payload."),

    S("solar-weather-lora-node", "Solar-Powered LoRa Weather Node", "Low-Power Sensor Networks", "Advanced",
      "esp32", ["bme280", "lora", "rtc", "sdcard"], "lora", hours=18, advanced=True,
      problem="Field weather nodes must survive months on a small solar panel, so duty cycle and sleep current dominate the design.",
      outcome="An ESP32 deep-sleeps between 15-minute samples, wakes from the RTC, measures, transmits one LoRa frame and returns to sleep.",
      objectives="Measure real sleep current with a power profiler|Use RTC alarm wakeup rather than the ESP32 timer|Buffer frames to SD when the gateway is unreachable",
      use_cases="Remote pasture weather|Mountain microclimate|Off-grid research",
      algorithm="Boot count in RTC memory decides whether to transmit or buffer; sensors are powered only during the awake window; deep sleep is entered after the radio TX completes.",
      logic="""char buf[160];
snprintf(buf, sizeof(buf), "W,%.1f,%.1f,%.1f,%s", temperature, humidity, pressure, timestamp);
payload = String(buf);
logLine = payload;
Serial.println(F("[INFO] Frame ready; esp_deep_sleep_start() is called by the scheduler"));""",
      tests="Measure awake and sleep current with a profiler and estimate battery life|Confirm an RTC alarm wake every 15 minutes|Verify buffered frames flush when the gateway returns",
      fails="Sleep current too high | Power down sensors with a MOSFET and disable the USB-UART bridge.|RTC alarm missed | Check the INT/SQW pin connection and battery.|LoRa duty-cycle violation | Reduce TX power and packet frequency per regional rules."),

    S("storm-risk-logger", "Thunderstorm Risk Logger", "Weather Stations & Forecasting", "Intermediate",
      "esp8266", ["bme280", "sound", "rtc", "sdcard"], "wifi_http", hours=10,
      problem="Storm research needs correlated pressure drops, humidity rises and acoustic events with reliable timestamps.",
      outcome="A NodeMCU logs pressure/humidity trends and loud-event counts to SD, then POSTs a summary when Wi-Fi is available.",
      objectives="Count threshold-crossing acoustic events|Correlate pressure drop with loud events|Handle limited ADC channels on ESP8266",
      use_cases="Storm-spotter prototype|School meteorology|Acoustic event logging",
      algorithm="A 5-minute sliding window counts sound_index excursions; a pressure fall below -1 hPa/h combined with events sets RISK=ELEVATED.",
      logic="""static uint16_t loudEvents = 0; static float p0 = 0;
if (sound_index > 75.0F) loudEvents++;
if (!p0) p0 = pressure;
float dP = pressure - p0;
const char* risk = (dP < -1.0F && loudEvents > 3) ? "ELEVATED" : "NORMAL";
char buf[200];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"dP_hpa\\":%.2f,\\"loud_events\\":%u,\\"risk\\":\\"%s\\"}", timestamp, dP, loudEvents, risk);
payload = String(buf); logLine = payload;""",
      tests="Generate three loud events and confirm the counter|Simulate a pressure drop and confirm ELEVATED|Verify the single A0 ADC handles the sound module with a divider",
      fails="Wi-Fi fails with ADC use | ESP8266 A0 is the only ADC; keep other sensors on I2C.|SD sharing SPI pins | Verify CS selection and 3.3 V level shifting.|False lightning claims | This logs acoustic events only; it does not detect lightning."),

    S("water-quality-buoy", "Floating Water-Quality Buoy", "Water Quality Monitoring", "Advanced",
      "esp32", ["ph", "tds", "turbidity", "ds18b20", "gsm"], "gsm", hours=20, advanced=True,
      problem="Ponds and tanks need multi-parameter water quality at locations without Wi-Fi, with probe fouling and power constraints.",
      outcome="A buoy samples pH, conductivity, turbidity and temperature, then sends an hourly cellular report with battery voltage.",
      objectives="Interface three analog probes with a level-shifter and ADC protection|Schedule probes to reduce fouling|Send hourly cellular batches",
      use_cases="Aquaculture pond|Reservoir spot monitoring|Irrigation source water",
      algorithm="Probes are powered only during a 30 s measurement window; a median-of-7 filter suppresses ripple; a quality flag marks out-of-range or disconnected probes.",
      logic="""bool bad = (ph_value < 0.0F || ph_value > 14.0F || turbidity_pct < 0.0F);
char buf[260];
snprintf(buf, sizeof(buf), "{\\"ph\\":%.2f,\\"tds_ppm\\":%.0f,\\"turbidity_idx\\":%.1f,\\"water_c\\":%.1f,\\"quality_ok\\":%s}", ph_value, tds_ppm, turbidity_pct, temperature, bad ? "false":"true");
payload = String(buf);""",
      tests="Dip probes in reference solutions and verify pH and TDS within tolerance|Confirm a turbidity increase with a clay suspension|Verify probes power down between samples",
      fails="pH and TDS interfere | Use isolated probe interfaces and a star ground.|Fouling after a week | Add a wiper or schedule manual cleaning.|Cellular signal poor | Use an external antenna and check the enclosure's RF transparency."),

    S("aquarium-water-monitor", "Aquarium Water-Quality Monitor", "Water Quality Monitoring", "Intermediate",
      "esp32", ["ds18b20", "ph", "tds", "oled", "buzzer"], "wifi_mqtt", hours=10,
      problem="Aquarium chemistry changes slowly, so small calibration errors and probe drift can trigger false alarms or hide real problems.",
      outcome="A monitor tracks temperature, pH and TDS with per-parameter hysteresis and a quiet-hours alert policy.",
      objectives="Store calibration constants per probe|Implement per-parameter hysteresis|Mute alerts during a configurable quiet window",
      use_cases="Freshwater aquarium|Aquaculture lab|Water chemistry lesson",
      algorithm="Each parameter has a warning band with 5 % hysteresis; alerts are aggregated into one message and suppressed during night hours.",
      logic="""static bool tempAlarm=false, phAlarm=false, tdsAlarm=false;
if (temperature > 28.0F) tempAlarm=true; if (temperature < 26.5F) tempAlarm=false;
if (ph_value < 6.5F || ph_value > 7.8F) phAlarm=true; else if (ph_value > 6.8F && ph_value < 7.5F) phAlarm=false;
if (tds_ppm > 500.0F) tdsAlarm=true; if (tds_ppm < 450.0F) tdsAlarm=false;
bool alert = tempAlarm || phAlarm || tdsAlarm;
digitalWrite(BUZZER_PIN, alert ? HIGH : LOW);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"water_c\\":%.1f,\\"ph\\":%.2f,\\"tds_ppm\\":%.0f,\\"alert\\":%s}", temperature, ph_value, tds_ppm, alert?"true":"false");
payload = String(buf);
displayLine = String(temperature,1) + "C pH" + String(ph_value,2);""",
      tests="Warm water above 28 °C and confirm the latched alarm|Move pH probe between buffers and check hysteresis|Confirm alerts are suppressed during quiet hours",
      fails="DS18B20 reads 85 °C | This is the power-on reset value; check the 4.7 kΩ pull-up.|Buzzer annoys at night | Verify the RTC/NTP quiet window logic.|pH jumps | Add isolation and keep probe cable away from pump wiring."),

    S("rainwater-harvesting-quality", "Rainwater Harvesting Quality Gate", "Water Quality Monitoring", "Intermediate",
      "esp32", ["turbidity", "ph", "rain", "valve"], "wifi_http", hours=11,
      problem="First-flush rainwater is dirty; diverting it requires a quality-based gate rather than a fixed timer.",
      outcome="A valve diverts water until turbidity and pH are within configured bands, then opens the collection path.",
      objectives="Use a two-parameter quality gate|Fail closed on sensor fault|Log diversion volume proxy",
      use_cases="Rainwater harvesting|Greywater prototype|Water reuse education",
      algorithm="A median-filtered turbidity index and pH must stay inside the band for 60 s before the divert valve releases; any sensor fault returns to divert.",
      logic="""static uint32_t goodSince = 0;
bool good = (turbidity_pct < 35.0F && ph_value > 6.0F && ph_value < 8.5F);
if (good) { if (!goodSince) goodSince = millis(); } else { goodSince = 0; }
bool collect = goodSince && (millis() - goodSince > 60000UL) && rain_pct > 20.0F;
digitalWrite(VALVE_PIN, collect ? HIGH : LOW);  // HIGH = collection path, LOW = divert
char buf[220];
snprintf(buf, sizeof(buf), "{\\"turbidity_idx\\":%.1f,\\"ph\\":%.2f,\\"rain_pct\\":%.1f,\\"collect\\":%s,\\"good_s\\":%lu}", turbidity_pct, ph_value, rain_pct, collect?"true":"false", goodSince?(unsigned long)((millis()-goodSince)/1000UL):0UL);
payload = String(buf);""",
      tests="Add clay to the sample and confirm the valve diverts|Restore clean water and confirm release after 60 s|Unplug turbidity probe and confirm fail-closed divert",
      fails="Valve energised permanently | Verify active-LOW vs active-HIGH module logic.|Turbidity reads full scale | Check the 5 V output divider and ADC range.|pH probe dries out | Keep it wet with storage solution; never measure dry."),

    S("under-sink-leak-alarm", "Under-Sink Leak Alarm with Instant Alert", "Water Leakage Detection", "Beginner",
      "esp32", ["water_leak", "buzzer", "led"], "wifi_mqtt", hours=5,
      problem="Leaks under sinks go unnoticed until damage is expensive; a low-voltage node must alert even if the cloud is down.",
      outcome="A leak rope triggers a local buzzer/LED immediately and publishes a latched MQTT alarm that must be acknowledged.",
      objectives="Debounce a conductive leak sensor|Latch an alarm until explicit acknowledgement|Keep local indication independent of the network",
      use_cases="Kitchen cabinet|Basement utility area|Server-room floor",
      algorithm="Two consecutive wet samples 2 s apart latch the alarm; an MQTT 'ack' command clears the cloud flag but not the local LED until dry.",
      logic="""static bool alarm = false; static uint8_t hits = 0;
if (leak_pct > 40.0F) { if (hits < 2) hits++; } else { hits = 0; }
if (hits >= 2) alarm = true;
if (alarm) { digitalWrite(BUZZER_PIN, HIGH); digitalWrite(LED_PIN, HIGH); }
else { digitalWrite(BUZZER_PIN, LOW); digitalWrite(LED_PIN, LOW); }
char buf[160];
snprintf(buf, sizeof(buf), "{\\"leak_pct\\":%.1f,\\"alarm\\":%s,\\"ack_required\\":true}", leak_pct, alarm?"true":"false");
payload = String(buf);""",
      tests="Wet the rope and confirm alarm within two samples|Disconnect Wi-Fi and confirm local buzzer still sounds|Send an ack and verify only the cloud flag clears",
      fails="False alarms from humidity | Raise the 40 % threshold and use a guarded cable.|No alert when offline | Verify the buzzer is driven before the MQTT code path.|Alarm never clears | Implement the 'ack' subscription callback."),

    S("multi-zone-leak-bus", "Multi-Zone Leak Detection over RS-485", "Water Leakage Detection", "Advanced",
      "esp32", ["water_leak", "rs485", "oled"], "rs485", hours=16, advanced=True,
      problem="Large buildings need many leak zones on one robust bus, but long analog cables pick up noise.",
      outcome="A Modbus RTU node exposes zone wetness registers and a local OLED status for a wired multi-drop installation.",
      objectives="Implement Modbus RTU slave behaviour|Terminate and bias an RS-485 bus correctly|Map sensor values into holding registers",
      use_cases="Plant room|Data centre|Multi-floor building",
      algorithm="Local leak_pct is mapped into a 0-1000 holding register with a fault code; the master polls the node and displays zone status locally.",
      logic="""uint16_t zoneReg = (uint16_t)(leak_pct * 10.0F);
bool zoneFault = (leak_pct < 0.0F || leak_pct > 100.0F);
char buf[160];
snprintf(buf, sizeof(buf), "{\\"zone\\":3,\\"wetness_x10\\":%u,\\"fault\\":%s,\\"reg_value\\":%.1f}", zoneReg, zoneFault?"true":"false", reg_value);
payload = String(buf);
displayLine = String("Z3 ") + String(leak_pct,0) + "% " + String(zoneFault?"FLT":"OK");""",
      tests="Poll the node with a Modbus master and verify register 0x0000|Wet the probe and confirm the register increases|Verify 120 Ω termination at both bus ends",
      fails="No Modbus response | Check DE/RE control and 9600 8N1 settings.|Frames corrupt on long cable | Use twisted pair, biasing resistors and lower baud rate.|Address conflict | Assign a unique slave ID per zone."),

    S("automatic-leak-shutoff", "Automatic Leak Shutoff Valve", "Water Leakage Detection", "Intermediate",
      "esp32", ["water_leak", "valve", "button", "buzzer"], "wifi_mqtt", hours=9,
      problem="Detection alone does not stop water damage; a shutoff needs a manual reset and a bounded valve duty cycle.",
      outcome="On confirmed leak the valve closes, a buzzer sounds, and only a physical button press reopens it after the probe is dry.",
      objectives="Implement a manual-reset safety interlock|Prevent valve coil overheating|Report state transitions with reasons",
      use_cases="Washing machine supply|Holiday-home protection|Lab water line",
      algorithm="A latched SHUT state requires dry sensor AND button press; valve energisation is limited to 5 s using a latching-valve driver.",
      logic="""static bool shut = false;
if (leak_pct > 40.0F) shut = true;
if (shut && pressed && leak_pct < 10.0F) shut = false;
digitalWrite(VALVE_PIN, shut ? HIGH : LOW);
digitalWrite(BUZZER_PIN, shut ? HIGH : LOW);
char buf[160];
snprintf(buf, sizeof(buf), "{\\"leak_pct\\":%.1f,\\"shut\\":%s,\\"reset_pressed\\":%s}", leak_pct, shut?"true":"false", pressed?"true":"false");
payload = String(buf);""",
      tests="Wet the probe and confirm shut state and buzzer|Press reset while still wet and confirm it stays shut|Dry the probe, press reset and confirm reopen",
      fails="Solenoid overheats | Use a latching valve or limit energisation to 5 s.|Button bounces | Add 50 ms debounce in firmware.|False shut from cleaning water | Move the probe or raise the threshold."),

    S("basement-flood-node", "Basement Flood Pump Controller", "Water Leakage Detection", "Advanced",
      "esp32", ["water_level", "water_leak", "pump", "gsm"], "gsm", hours=15, advanced=True,
      problem="Flood pumps fail silently; cellular alerting and a redundant sensor path are needed when the property is unattended.",
      outcome="A controller starts a pump on rising level, detects disagreement between level and rope sensors, and sends a cellular fault message.",
      objectives="Use two independent sensing methods|Detect sensor disagreement|Alert over cellular with a daily self-test",
      use_cases="Basement sump|Remote pump house|Utility room",
      algorithm="Level > 60 % OR rope > 50 % starts the pump; disagreement for > 2 min marks a sensor fault; a daily self-test runs the pump for 2 s.",
      logic="""bool wetRope = leak_pct > 50.0F;
bool highLevel = level_pct > 60.0F;
static uint32_t disagreeAt = 0;
bool disagree = (wetRope != highLevel);
if (disagree) { if (!disagreeAt) disagreeAt = millis(); } else disagreeAt = 0;
bool fault = disagreeAt && millis()-disagreeAt > 120000UL;
digitalWrite(PUMP_PIN, (wetRope || highLevel) ? HIGH : LOW);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"level_pct\\":%.1f,\\"leak_pct\\":%.1f,\\"pump\\":%s,\\"sensor_fault\\":%s}", level_pct, leak_pct, (wetRope||highLevel)?"true":"false", fault?"true":"false");
payload = String(buf);""",
      tests="Raise the float sensor and confirm pump start|Wet only the rope and confirm disagreement fault after 2 min|Confirm the daily 2 s self-test message",
      fails="Pump runs dry | Add a minimum water-level interlock and an over-temperature cut-out.|Cellular message delayed | Batch alerts and check signal strength.|Float sticks | Add a scheduled physical inspection."),

    S("rfid-access-lock", "RFID Access Lock with Audit Trail", "Home Automation", "Intermediate",
      "esp32", ["rfid", "relay", "rtc", "buzzer", "oled"], "wifi_mqtt", hours=12,
      problem="UID-only RFID is easy to clone; a learning build must show the limitation while still providing a working audit trail.",
      outcome="A reader grants low-voltage DC lock actuation to allow-listed UIDs, logs every decision with an RTC timestamp and plays distinct tones.",
      objectives="Read MFRC522 UIDs over SPI|Maintain an allow-list with local override|Log decisions and explain UID cloning risk",
      use_cases="Makerspace cabinet|Lab equipment drawer|Access-control lesson",
      algorithm="UID strings are compared to a hashed allow-list; granted access energises the relay for 3 s and appends a timestamped audit row.",
      logic="""bool granted = (uid == "a1b2c3d4" || uid == "deadbeef");  // replace with hashed allow-list
static uint32_t unlockedAt = 0;
if (granted) { unlockedAt = millis(); digitalWrite(RELAY_PIN, LOW); digitalWrite(BUZZER_PIN, HIGH); }
if (unlockedAt && millis() - unlockedAt > 3000UL) { digitalWrite(RELAY_PIN, HIGH); digitalWrite(BUZZER_PIN, LOW); unlockedAt = 0; }
char buf[200];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"uid\\":\\"%s\\",\\"granted\\":%s,\\"security_note\\":\\"UID_only_cloneable\\"}", timestamp, uid.c_str(), granted?"true":"false");
payload = String(buf);
displayLine = granted ? "ACCESS OK" : "DENIED";""",
      tests="Present an allow-listed tag and confirm 3 s relay pulse|Present an unknown tag and confirm denial tone|Verify each decision appears in the MQTT audit topic",
      fails="MFRC522 not responding | Check SPI CS/RST wiring and 3.3 V only power.|Relay clicks but load stays off | Verify active-LOW logic and external 5 V supply.|UID mismatch case | Normalise hex case before comparison."),

    S("smart-doorbell-camera", "Low-Cost Smart Doorbell with Camera", "Home Automation", "Advanced",
      "esp32cam", ["camera", "button", "buzzer"], "wifi_http", hours=16, advanced=True,
      problem="Cloud doorbells raise privacy concerns; a local ESP32-CAM build should capture on demand and expose the limits of the hardware.",
      outcome="Pressing a button captures a JPEG, sounds a local buzzer and POSTs the frame metadata and image to a self-hosted endpoint.",
      objectives="Initialise the OV2640 camera with correct pin config|Trigger a capture from a debounced button|Handle PSRAM and frame-buffer failures",
      use_cases="Privacy-respecting doorbell|Local image capture lab|Edge vision intro",
      algorithm="A button ISR sets a flag; loop() captures one frame, checks PSRAM availability, builds a multipart-ish payload and reports byte count.",
      logic="""bool ring = !digitalRead(BUTTON_PIN);
if (ring) {
  char buf[180];
  snprintf(buf, sizeof(buf), "{\\"event\\":\\"doorbell\\",\\"jpeg_bytes\\":%u,\\"privacy\\":\\"self_hosted_only\\"}", (unsigned)jpeg_bytes);
  payload = String(buf);
  digitalWrite(BUZZER_PIN, HIGH); delay(120); digitalWrite(BUZZER_PIN, LOW);
} else { payload = "{\\"event\\":\\"heartbeat\\"}"; }""",
      tests="Press the button and confirm a JPEG on the local endpoint|Verify a boot with PSRAM disabled is rejected with a clear log|Measure capture-to-POST latency",
      fails="Camera init failed | Select AI-Thinker ESP32-CAM pin map and enable PSRAM.|Brownout on Wi-Fi TX | Use a 5 V / 1 A supply with short wires.|Frame buffer NULL | Return each fb and lower JPEG quality/framesize."),

    S("multi-room-climate-automation", "Multi-Room Climate Automation Node", "Home Automation", "Advanced",
      "esp32s3", ["sht31", "pir", "relay", "oled"], "wifi_mqtt", hours=14, advanced=True,
      problem="Heating/cooling a room nobody occupies wastes energy, but occupancy alone is not enough to decide comfort.",
      outcome="A node combines occupancy, temperature and humidity into a comfort score that drives a low-voltage DC relay with a minimum off-time.",
      objectives="Fuse presence and climate into a comfort decision|Implement compressor-style minimum off-time|Expose a manual override topic",
      use_cases="Home office HVAC assist|Small server room|Comfort research",
      algorithm="A comfort score penalises deviation from 22 °C/50 %RH; a 5-minute minimum-off timer protects the load; occupancy absence forces OFF.",
      logic="""float comfort = 100.0F - fabsf(temperature - 22.0F)*8.0F - fabsf(humidity - 50.0F)*0.8F;
static uint32_t lastOff = 0;
bool want = motion && comfort < 70.0F;
bool allowed = millis() - lastOff > 300000UL;
bool on = want && allowed;
if (!on && lastOff == 0) lastOff = millis();
digitalWrite(RELAY_PIN, on ? LOW : HIGH);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"occupancy\\":%s,\\"comfort\\":%.1f,\\"relay\\":%s}", temperature, humidity, motion?"true":"false", comfort, on?"true":"false");
payload = String(buf);
displayLine = String("Comfort ") + String(comfort,0);""",
      tests="Simulate occupancy with low comfort and confirm relay ON|Remove occupancy and confirm OFF|Cycle rapidly and confirm 5-minute minimum off-time",
      fails="Relay chatters | Increase hysteresis and minimum off-time.|PIR false negatives | Use mmWave radar or a longer timeout.|No manual override | Implement an MQTT override with an expiry."),

    S("appliance-energy-guard", "Appliance Energy Guard with Remote Cutoff", "Home Automation", "Intermediate",
      "esp32", ["relay", "ina219", "button"], "wifi_mqtt", hours=9,
      problem="Appliances left on standby waste power; cutting them off needs current measurement and a physical local override.",
      outcome="A low-voltage DC load is monitored; standby below a threshold for 10 minutes triggers cutoff, with a physical button to restore.",
      objectives="Detect standby from current draw|Implement a delayed cutoff and local override|Keep relay state consistent with telemetry",
      use_cases="Workbench power control|Charging station|Standby-killer lesson",
      algorithm="A 10-minute low-current timer closes the relay; the button resets the timer; overcurrent immediately opens the relay and latches a fault.",
      logic="""static uint32_t lowSince = 0; static bool fault = false;
if (fabsf(current_ma) > 2500.0F) { fault = true; }
if (pressed) { fault = false; lowSince = 0; }
if (fabsf(current_ma) < 40.0F) { if (!lowSince) lowSince = millis(); } else lowSince = 0;
bool off = fault || (lowSince && millis()-lowSince > 600000UL);
digitalWrite(RELAY_PIN, off ? HIGH : LOW);
char buf[200];
snprintf(buf, sizeof(buf), "{\\"v\\":%.2f,\\"ma\\":%.1f,\\"w\\":%.2f,\\"cutoff\\":%s,\\"fault\\":%s}", voltage_v, current_ma, power_w, off?"true":"false", fault?"true":"false");
payload = String(buf);""",
      tests="Connect a 100 mA load and confirm no cutoff|Drop below 40 mA for 10 min and confirm cutoff|Trigger >2.5 A and confirm immediate latched fault",
      fails="Current offset causes false standby | Zero the INA219 offset and set the correct shunt value.|Button press ignored | Add debounce and check INPUT_PULLUP inversion.|Relay weld risk | Use a properly rated DC relay and never switch inductive mains loads here."),
]
