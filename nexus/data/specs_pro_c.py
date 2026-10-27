"""Pro library part C: waste, transport, logistics, healthcare, a11y, wearables, robotics."""
from .spec_base import S

SPECS = [
    S("smart-bin-fill-level", "Smart Waste-Bin Fill-Level Sensor", "Waste Management", "Intermediate",
      "esp32", ["vl53l0x", "lora", "rtc"], "lora", hours=10,
      problem="Collection trucks visit empty bins; a fill-level node must survive months on a battery in a dirty enclosure.",
      outcome="A ToF sensor reports bin fill percentage over LoRa with a scheduled collection flag and a battery-health heartbeat.",
      objectives="Convert distance to fill percentage using a measured bin height|Sleep between readings|Flag implausible readings as sensor faults",
      use_cases="Municipal bin trial|Campus waste study|Recycling point monitoring",
      algorithm="Distance from lid to waste gives fill %; three consecutive readingsgate a collection flag; out-of-range distances are marked as optical faults.",
      logic="""float fill = constrain((BIN_HEIGHT_CM - distance_cm) / BIN_HEIGHT_CM * 100.0F, 0.0F, 100.0F);
static uint8_t hits = 0;
if (fill > 80.0F) { if (hits < 3) hits++; } else hits = 0;
char buf[140];
snprintf(buf, sizeof(buf), "B,%.0f,%s,%s", fill, hits >= 3 ? "COLLECT":"OK", (distance_cm < 2.0F || distance_cm > 200.0F) ? "OPTICAL_FAULT":"OK");
payload = String(buf);""",
      tests="Place a target at 10 cm and verify fill percentage|Cover the sensor and confirm OPTICAL_FAULT|Measure sleep current and estimate battery life",
      fails="Fill always 100 % | Measure BIN_HEIGHT_CM for the real bin and check sensor mounting angle.|Dark liners absorb IR | Increase the timing budget or use an ultrasonic sensor.|LoRa range short | Use an external antenna and keep the bin lid RF-transparent."),

    S("bin-fire-alert", "Waste-Bin Temperature and Smoke Alert", "Waste Management", "Advanced",
      "picow", ["ds18b20", "gas_mq2", "gsm"], "gsm", hours=15, advanced=True,
      problem="Bin fires spread quickly; a low-cost node must detect a thermal rise and smoke trend without presenting itself as a certified alarm.",
      outcome="A Pico W node sends a cellular alert when temperature rises faster than 3 °C/min and the smoke index exceeds a baseline.",
      objectives="Detect a rate-of-rise, not just an absolute temperature|Baseline a gas sensor outdoors|State the safety limitation explicitly",
      use_cases="Recycling yard|Industrial waste skip|Fire-safety research",
      algorithm="A 60 s slope and a slow smoke baseline are combined; alerts are labelled ADVISORY and require human verification.",
      logic="""static float lastT = temperature, smokeBase = gas_index;
float rate = (temperature - lastT) / (SAMPLE_INTERVAL_MS / 60000.0F); lastT = temperature;
smokeBase = smokeBase * 0.99F + gas_index * 0.01F;
bool advisory = (rate > 3.0F && gas_index > smokeBase * 1.5F);
char buf[200];
snprintf(buf, sizeof(buf), "{\\"temp_c\\":%.1f,\\"rate_c_min\\":%.2f,\\"smoke_idx\\":%.1f,\\"alert\\":%s,\\"class\\":\\"ADVISORY_NOT_CERTIFIED\\"}", temperature, rate, gas_index, advisory?"true":"false");
payload = String(buf);""",
      tests="Warm the probe quickly and confirm an advisory with smoke|Confirm no alert from slow daily warming|Verify the payload says NOT_CERTIFIED",
      fails="Heater drains battery | Duty-cycle the MQ heater with a MOSFET.|False smoke baseline outdoors | Re-baseline weekly and log humidity.|Cellular dead zone | Use an external antenna or a LoRa gateway."),

    S("recycling-sorter-prototype", "RFID-Guided Recycling Sorter Prototype", "Waste Management", "Advanced",
      "esp32", ["rfid", "vl53l0x", "servo", "buzzer"], "wifi_mqtt", hours=17, advanced=True,
      problem="Sorting demo rigs need to identify an item, confirm its presence and actuate a gate with a bounded duty cycle.",
      outcome="A conveyor model reads an item tag, confirms it with ToF presence and diverts it with a servo gate.",
      objectives="Associate an RFID UID with a material class|Confirm object presence before actuation|Log sorting decisions and jams",
      use_cases="Recycling education|Sorting research|Factory training rig",
      algorithm="A UID lookup table picks a gate angle; a ToF reading gates the actuation; a 2 s timeout closes the gate and logs a miss.",
      logic="""static uint32_t gateAt = 0;
int targetAngle = (uid == "a1b2c3d4") ? 75 : 15;
bool present = (distance_cm > 2.0F && distance_cm < 15.0F);
if (uid.length() && present) { gateAt = millis(); actuator.write(targetAngle); }
if (gateAt && millis()-gateAt > 2000UL) { actuator.write(15); gateAt = 0; }
char buf[200];
snprintf(buf, sizeof(buf), "{\\"uid\\":\\"%s\\",\\"distance_cm\\":%.1f,\\"gate_deg\\":%d,\\"present\\":%s}", uid.c_str(), distance_cm, gateAt?targetAngle:15, present?"true":"false");
payload = String(buf);""",
      tests="Present a tagged item and confirm the gate opens|Present an untagged item and confirm no action|Verify the gate closes after 2 s",
      fails="Servo stalls | Check the external 5 V supply and mechanical binding.|UID read unreliable | Move the antenna away from metal and slow the conveyor.|ToF misses black plastic | Use a longer timing budget or an IR break-beam."),

    S("landfill-leachate-monitor", "Landfill Leachate Quality Monitor", "Waste Management", "Advanced",
      "esp32", ["ph", "turbidity", "water_leak", "lora"], "lora", hours=18, advanced=True,
      problem="Leachate collection points are remote and corrosive; probes need isolation, fault detection and long-range reporting.",
      outcome="A LoRa node reports pH, turbidity index and leak presence with a probe-health flag and a conservative alert policy.",
      objectives="Isolate three analog probe interfaces|Detect disconnected/fouled probes|Transmit a compact status frame",
      use_cases="Landfill research|Industrial effluent education|Remote water monitoring",
      algorithm="Each probe is range-checked; two consecutive faults mark a probe unhealthy; a frame is sent every 15 minutes or on a new fault.",
      logic="""bool phOk = ph_value > 1.0F && ph_value < 13.0F;
bool turbOk = turbidity_pct >= 0.0F && turbidity_pct <= 100.0F;
bool leak = leak_pct > 45.0F;
char buf[160];
snprintf(buf, sizeof(buf), "L,%.2f,%.1f,%s,%s", ph_value, turbidity_pct, leak?"LEAK":"DRY", (phOk&&turbOk)?"PROBES_OK":"PROBE_FAULT");
payload = String(buf);""",
      tests="Dip the pH probe in buffers and confirm range checks|Add clay to water and confirm turbidity rises|Disconnect a probe and confirm PROBE_FAULT",
      fails="Probe cross-talk | Use isolated analog front ends and a star ground.|Fouling in days | Add a cleaning schedule and a protective cage.|LoRa frames collide | Stagger transmission by node ID."),

    S("ultrasonic-parking-spot", "Ultrasonic Smart Parking Spot Indicator", "Smart Transportation & Parking", "Intermediate",
      "esp32", ["hcsr04", "led", "buzzer"], "wifi_mqtt", hours=8,
      problem="Drivers circle car parks needlessly; a per-spot indicator must distinguish a car from a person or a stray echo.",
      outcome="A node decides OCCUPIED/FREE with time hysteresis and publishes state changes with the raw distance.",
      objectives="Debounce ultrasonic occupancy|Handle out-of-range echoes|Publish state only on change",
      use_cases="Private car park|Driveway monitor|Garage bay",
      algorithm="A distance below 80 cm for 5 s marks occupied; above 100 cm for 5 s marks free; invalid echoes are ignored.",
      logic="""static const char* spot = "FREE"; static uint32_t changeAt = 0; static const char* candidate = "FREE";
const char* now = (distance_cm > 2.0F && distance_cm < 80.0F) ? "OCCUPIED" : (distance_cm > 100.0F ? "FREE" : candidate);
if (strcmp(now, candidate)) { candidate = now; changeAt = millis(); }
if (strcmp(candidate, spot) && millis()-changeAt > 5000UL) { spot = candidate; }
digitalWrite(LED_PIN, strcmp(spot,"OCCUPIED") == 0 ? HIGH : LOW);
char buf[160];
snprintf(buf, sizeof(buf), "{\\"distance_cm\\":%.1f,\\"spot\\":\\"%s\\",\\"echo_valid\\":%s}", distance_cm, spot, distance_cm>0.0F?"true":"false");
payload = String(buf);""",
      tests="Park a box 40 cm away and confirm OCCUPIED after 5 s|Remove it and confirm FREE after 5 s|Point at open sky and confirm no state flapping",
      fails="False occupancy from echoes | Narrow the sensor cone and add a median filter.|Water on the transducer | Use a waterproof JSN-SR04T sensor outdoors.|ECHO above 3.3 V | Verify the 1 kΩ/2 kΩ divider."),

    S("parking-gateway", "LoRa Parking Gateway on Raspberry Pi", "Smart Transportation & Parking", "Advanced",
      "rpi4", ["lora", "ethernet", "oled"], "ethernet", hours=18, advanced=True,
      problem="Many LoRa spot sensors need one gateway that decodes frames, deduplicates them and bridges to MQTT.",
      outcome="A Raspberry Pi gateway parses LoRa frames, deduplicates by node/sequence and republishes occupancy to an MQTT broker.",
      objectives="Receive LoRa frames on a Linux host|Validate frame structure and deduplicate|Expose gateway health metrics",
      use_cases="Private car park|Campus parking|LoRaWAN bridge prototype",
      algorithm="Python SPI driver reads the SX1278 FIFO; frames are checked for prefix/length, deduplicated by sequence number and forwarded over MQTT.",
      logic="""# Python gateway logic generated in the Python firmware section.
payload = "{\\"gateway\\":\\"rpi4_lora\\",\\"spots\\":8,\\"dedupe\\":true}";""",
      tests="Send 8 simulated node frames and confirm 8 MQTT updates|Send a duplicate frame and confirm it is dropped|Verify gateway health metrics are published",
      fails="SPI permission denied | Enable SPI with raspi-config and add the user to the spi group.|CRC errors | Check the antenna and wiring; use a shorter cable.|MQTT backlog | Batch updates and use QoS 1."),

    S("bicycle-lane-counter", "Bicycle Lane Counter and Speed Estimator", "Smart Transportation & Parking", "Advanced",
      "esp32", ["pir", "vl53l0x", "sdcard"], "sd_local", hours=13, advanced=True,
      problem="Traffic planners need anonymous bicycle counts without cameras; a single sensor confuses pedestrians and bikes.",
      outcome="A two-signature logger counts ToF-confirmed PIR events and estimates speed from a known beam separation, logging locally.",
      objectives="Combine two sensing modalities anonymously|Estimate speed from timing|Store only anonymous counts",
      use_cases="Campus bike lane|Trail counter|Traffic-calming study",
      algorithm="A PIR rising edge starts a timer; a ToF near-distance event within 1.2 s confirms a bike-like object; speed = beam spacing / delta time.",
      logic="""static uint32_t pirAt = 0; static uint32_t bikes = 0;
if (motion && !pirAt) pirAt = millis();
bool near = distance_cm > 5.0F && distance_cm < 60.0F;
if (pirAt && near) {
  float dt = (millis()-pirAt)/1000.0F;
  if (dt > 0.05F && dt < 1.2F) {
    bikes++;
    char buf[160];
    snprintf(buf, sizeof(buf), "%lu,%lu,%.2f,%.2f", (unsigned long)bikes, (unsigned long)millis(), dt, 0.8F/dt);
    payload = String(buf); logLine = payload;
  }
  pirAt = 0;
}
if (pirAt && millis()-pirAt > 1500UL) pirAt = 0;""",
      tests="Wave a large object through both sensors and confirm one count|Walk slowly and confirm a low speed estimate|Verify no images or identifiers are stored",
      fails="Pedestrians counted as bikes | Adjust the distance window and timing; add a second beam.|Missed fast cyclists | Increase the sampling rate to 20 Hz.|SD wear | Batch writes and use a high-endurance card."),

    S("traffic-noise-air-node", "Roadside Noise and Air-Quality Node", "Smart Transportation & Parking", "Advanced",
      "picow", ["sound", "pms5003", "gps"], "wifi_http", hours=16, advanced=True,
      problem="Roadside exposure studies need synchronised noise, particulate and location data at low cost.",
      outcome="A Pico W node posts 1-minute aggregates of sound index, PM2.5 and GPS coordinates to an HTTP endpoint.",
      objectives="Aggregate high-rate sensor samples locally|Geotag each minute|Separate traffic peaks from background",
      use_cases="School street study|Urban planning research|Exposure mapping",
      algorithm="Sound is sampled at 20 Hz and aggregated into Leq-like energy; PM samples are averaged; both are tagged with the last valid GPS fix.",
      logic="""static float soundSum = 0, pmSum = 0; static uint16_t n = 0;
soundSum += sound_index; pmSum += pm25; n++;
if (n >= 12) {
  char buf[230];
  snprintf(buf, sizeof(buf), "{\\"lat\\":%.6f,\\"lng\\":%.6f,\\"sound_idx_avg\\":%.1f,\\"pm25_avg\\":%.1f,\\"samples\\":%u}", lat, lng, soundSum/n, pmSum/n, n);
  payload = String(buf); soundSum = pmSum = 0; n = 0;
} else payload = "";""",
      tests="Clap repeatedly and confirm the sound aggregate rises|Compare PM with a co-located reference|Verify coordinates are present in each POST",
      fails="Sound module saturates | Lower gain or replace with an I2S MEMS microphone.|GPS fix slow | Use an external antenna and cache the last valid fix.|HTTP timeouts | Buffer locally and retry with backoff."),

    S("gps-asset-tracker", "Cellular GPS Asset Tracker", "Logistics & Asset Tracking", "Advanced",
      "esp32", ["gps", "gsm", "rtc"], "gsm", hours=15, advanced=True,
      problem="Assets move outside Wi-Fi range; a tracker needs position, time and a power-aware reporting policy.",
      outcome="A tracker reports position over cellular only when it moves more than 100 m or a 30-minute heartbeat is due.",
      objectives="Use GPS plus RTC for timekeeping|Suppress redundant position reports|Buffer positions during coverage gaps",
      use_cases="Trailer tracking|Equipment hire|Field asset audit",
      algorithm="Haversine distance from the last reported fix gates transmissions; a buffer stores up to 100 unsent positions.",
      logic="""static double lastLat = 0, lastLng = 0; static uint32_t lastSend = 0;
double dLat = (lat-lastLat)*111320.0, dLng = (lng-lastLng)*111320.0*cos(lat*0.01745);
double moved = sqrt(dLat*dLat + dLng*dLng);
if (moved > 100.0 || millis()-lastSend > 1800000UL) {
  lastSend = millis(); lastLat = lat; lastLng = lng;
  char buf[200];
  snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"lat\\":%.6f,\\"lng\\":%.6f,\\"moved_m\\":%.0f}", timestamp, lat, lng, moved);
  payload = String(buf);
} else payload = "";""",
      tests="Move the unit >100 m and confirm a cellular fix|Leave stationary and confirm only heartbeats|Disable the antenna and confirm buffered records",
      fails="GPS fix takes minutes | Use an active antenna and a clear sky view.|Modem reboots on TX | Provide 2 A peak and 1000 µF capacitance.|Data cost high | Increase the movement threshold and heartbeat interval."),

    S("cold-chain-parcel-logger", "Cold-Chain Parcel Shock and Temperature Logger", "Logistics & Asset Tracking", "Intermediate",
      "esp32", ["ds18b20", "mpu6050", "sdcard", "rtc"], "sd_local", hours=11,
      problem="A parcel can be within temperature limits yet damaged by a drop; both need time-stamped evidence.",
      outcome="A logger records temperature excursions and shock events above 2 g to SD with RTC timestamps.",
      objectives="Detect shock from accelerometer magnitude|Log temperature excursions|Protect the SD log from power loss",
      use_cases="Pharmaceutical sample shipping|Food delivery audit|Fragile parcel study",
      algorithm="Each 5 s window records maximum vibration_g and temperature; shocks above 2 g are written immediately with a sequence number.",
      logic="""static uint32_t seq = 0; seq++;
bool shock = vibration_g > 2.0F || fabsf(ax) > 25.0F || fabsf(ay) > 25.0F;
char buf[220];
snprintf(buf, sizeof(buf), "%lu,%s,%.1f,%.3f,%s", (unsigned long)seq, timestamp, temperature, vibration_g, shock?"SHOCK":"ok");
payload = String(buf); logLine = payload;
if (shock) Serial.println(F("[EVENT] Shock recorded"));""",
      tests="Drop the logger from 20 cm onto foam and confirm a SHOCK row|Warm the probe and confirm temperature rise|Power-cycle and confirm the log is intact",
      fails="False shocks on handling | Raise the threshold and require two consecutive samples.|IMU axis scaling wrong | Verify the ±4 g range setting in the library.|Timestamp lost | Replace the RTC coin cell."),

    S("pallet-shock-monitor", "LoRa Pallet Shock Monitor", "Logistics & Asset Tracking", "Advanced",
      "esp32", ["mpu6050", "lora"], "lora", hours=13, advanced=True,
      problem="Warehouses need shock alerts from pallets without wiring or frequent battery changes.",
      outcome="A LoRa node sends a compact shock event frame with peak g and a rolling event counter.",
      objectives="Detect peak acceleration with a low-power IMU|Transmit only on events plus heartbeat|Keep the frame small",
      use_cases="Fragile goods pallet|Forklift monitoring|Warehouse research",
      algorithm="Peak magnitude over a 1 s window is compared to 2.5 g; events are transmitted immediately with a daily heartbeat.",
      logic="""static float peak = 0; static uint16_t events = 0; static uint32_t lastHb = 0;
peak = fmaxf(peak, vibration_g);
if (peak > 2.5F) { events++; char buf[100]; snprintf(buf, sizeof(buf), "P,%u,%.2f,EVENT", events, peak); payload = String(buf); }
else if (millis()-lastHb > 86400000UL) { lastHb = millis(); payload = String("P,") + events + ",0.00,HB"; }
else payload = "";
peak = 0;""",
      tests="Tap the sensor sharply and confirm an EVENT frame|Confirm one daily heartbeat|Measure current draw and estimate battery life",
      fails="IMU missed short shocks | Raise the sample rate or use the MPU6050 interrupt pin.|LoRa duty cycle exceeded | Rate-limit events per minute.|Battery drains | Use deep sleep and wake-on-motion."),

    S("forklift-tracker", "Warehouse Forklift Zone Tracker", "Logistics & Asset Tracking", "Advanced",
      "esp32", ["rfid", "gps", "oled"], "wifi_mqtt", hours=14, advanced=True,
      problem="Indoor forklifts have no GPS; zone tracking needs low-cost landmarks and a clear indoor/outdoor switch.",
      outcome="A node uses RFID floor tags as indoor landmarks and GPS outdoors, reporting the current zone with a source flag.",
      objectives="Use RFID tags as low-cost zone markers|Fall back to GPS outdoors|Report confidence source per update",
      use_cases="Warehouse fleet|Yard logistics|Asset-flow study",
      algorithm="A scanned UID maps to a zone table; GPS is used only when a valid fix exists; the active source is published with every update.",
      logic="""static String zone = "UNKNOWN";
if (uid.length()) zone = (uid == "a1b2c3d4") ? "DOCK_A" : (uid == "deadbeef") ? "AISLE_3" : zone;
bool gpsValid = (fabs(lat) > 0.0001 || fabs(lng) > 0.0001);
const char* source = uid.length() ? "RFID" : (gpsValid ? "GPS" : "STALE");
char buf[200];
snprintf(buf, sizeof(buf), "{\\"zone\\":\\"%s\\",\\"source\\":\\"%s\\",\\"lat\\":%.5f,\\"lng\\":%.5f}", zone.c_str(), source, lat, lng);
payload = String(buf);
displayLine = String(zone) + " " + String(source);""",
      tests="Scan two different tags and confirm zone changes|Move outdoors and confirm GPS source|Verify STALE appears with no landmarks or fix",
      fails="RFID range too short | Use larger antennas or read at the tyre line.|GPS never valid indoors | Rely on RFID only and mark GPS as unavailable.|Zone flapping | Add a 10 s dwell filter."),

    S("hand-hygiene-monitor", "Hand-Hygiene Station Usage Monitor", "Healthcare & Wellness Prototypes", "Intermediate",
      "esp32", ["vl53l0x", "led", "buzzer"], "wifi_mqtt", hours=9,
      problem="Manual hand-hygiene audits are unreliable; an anonymous counter must avoid cameras and personal data.",
      outcome="A ToF sensor counts anonymous dispenser activations with a 3 s lockout and a local reminder LED.",
      objectives="Detect a hand without identifying a person|Debounce repeated activations|Publish only aggregate counts",
      use_cases="Clinic entrance (educational)|School hygiene study|Workspace hygiene nudge",
      algorithm="A near-distance event (< 12 cm) triggers one count with a 3 s lockout; no images or identifiers are stored.",
      logic="""static uint32_t count = 0; static uint32_t lastAt = 0;
bool handNear = distance_cm > 2.0F && distance_cm < 12.0F;
if (handNear && millis()-lastAt > 3000UL) {
  count++; lastAt = millis();
  digitalWrite(LED_PIN, HIGH); digitalWrite(BUZZER_PIN, HIGH); delay(80);
  digitalWrite(BUZZER_PIN, LOW);
}
if (millis()-lastAt > 1000UL) digitalWrite(LED_PIN, LOW);
char buf[150];
snprintf(buf, sizeof(buf), "{\\"dispenser_uses\\":%lu,\\"anonymous\\":true,\\"medical_device\\":false}", (unsigned long)count);
payload = String(buf);""",
      tests="Wave a hand 10 times with pauses and confirm 10 counts|Hold a hand still and confirm no repeats|Verify no personal data appears in the payload",
      fails="Double counts | Increase the lockout and require a far-to-near transition.|ToF reads skin poorly | Increase timing budget and sensor gain.|False compliance claims | Keep the non-medical-device flag in the UI."),

    S("medication-reminder-device", "Offline Medication Reminder Device", "Healthcare & Wellness Prototypes", "Beginner",
      "esp32", ["rtc", "buzzer", "oled", "button"], "serial", hours=6,
      problem="Phone reminders fail for users with limited tech access; an offline device needs a clear display and an acknowledge button.",
      outcome="A battery-backed RTC triggers audible/visual reminders at configured times until the user acknowledges them.",
      objectives="Schedule reminders from RTC time|Require an explicit acknowledgement|Explain wellness-only limitations",
      use_cases="Elderly support prototype|Classroom scheduling demo|Habit tracker",
      algorithm="A schedule array is compared with the RTC HH:MM; an active reminder repeats every 60 s until the button clears it.",
      logic="""static bool active = false; static uint32_t lastBeep = 0;
int hh = atoi(timestamp + 11), mm = atoi(timestamp + 14);
if ((hh == 8 && mm == 0) || (hh == 20 && mm == 0)) active = true;
if (pressed) active = false;
if (active && millis()-lastBeep > 60000UL) { lastBeep = millis(); digitalWrite(BUZZER_PIN, HIGH); delay(200); digitalWrite(BUZZER_PIN, LOW); }
char buf[160];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"reminder\\":%s,\\"ack\\":%s,\\"medical_device\\":false}", timestamp, active?"true":"false", pressed?"true":"false");
payload = String(buf);
displayLine = active ? "REMINDER - press btn" : "Next 08:00 / 20:00";""",
      tests="Set the RTC to 07:59 and confirm the 08:00 reminder|Press the button and confirm it clears|Remove power and confirm the RTC keeps time",
      fails="RTC loses time | Replace the coin cell and set the clock once.|Buzzer too quiet | Use an active buzzer rated for 3.3 V.|Missed window | Compare HH:MM every cycle, not exact equality of seconds."),

    S("posture-wellness-wearable", "Posture Wellness Wearable", "Healthcare & Wellness Prototypes", "Intermediate",
      "picow", ["mpu6050", "buzzer"], "ble", hours=10,
      problem="Posture gadgets often make medical claims; a transparent wellness prototype should expose its raw tilt angle and limits.",
      outcome="A Pico W wearable estimates torso tilt from accelerometer axes and gently buzzes after 30 s of poor posture.",
      objectives="Compute tilt from static acceleration|Require sustained poor posture|Label the device as non-medical",
      use_cases="Desk posture nudge|Ergonomics class|Wearable prototyping",
      algorithm="Tilt = atan2(ax, az) in degrees; a > 25° deviation sustained for 30 s triggers one short vibration-style buzz.",
      logic="""float tilt = atan2f(ax, az) * 57.2958F;
static uint32_t badSince = 0;
if (fabsf(tilt) > 25.0F) { if (!badSince) badSince = millis(); } else badSince = 0;
bool alert = badSince && millis()-badSince > 30000UL;
if (alert) { digitalWrite(BUZZER_PIN, HIGH); delay(100); digitalWrite(BUZZER_PIN, LOW); badSince = 0; }
char buf[180];
snprintf(buf, sizeof(buf), "{\\"tilt_deg\\":%.1f,\\"poor_posture_s\\":%lu,\\"medical_device\\":false}", tilt, badSince?(unsigned long)((millis()-badSince)/1000UL):0UL);
payload = String(buf);""",
      tests="Tilt the sensor >25° for 30 s and confirm one buzz|Return upright and confirm no further alerts|Verify the non-medical flag in every payload",
      fails="Tilt noisy during walking | Low-pass the acceleration and ignore high dynamic motion.|Battery drains | Use deep sleep and BLE connection intervals.|Skin irritation | Use a biocompatible strap and a protected cell."),

    S("pulse-wellness-prototype", "Pulse-Rate Wellness Prototype", "Healthcare & Wellness Prototypes", "Advanced",
      "esp32", ["max30102", "oled"], "ble", hours=14, advanced=True,
      problem="Optical heart-rate sensors are easy to misread; a learning prototype must separate signal quality from the BPM estimate.",
      outcome="A MAX30102 node displays an estimated BPM only when the IR signal quality passes a threshold, with an explicit non-medical label.",
      objectives="Evaluate IR signal quality before estimating BPM|Implement a simple peak detector|Explain SpO₂ calibration limits",
      use_cases="Wellness demo|Signal-processing lesson|Wearable research",
      algorithm="A moving threshold on the IR signal detects peaks; inter-peak intervals are median-filtered into BPM; low-perfusion samples are rejected.",
      logic="""static float threshold = 50000.0F; static uint32_t lastPeak = 0; static float bpmEst = 0;
threshold = threshold * 0.95F + (float)irValue * 0.05F;
if ((float)irValue > threshold * 1.02F && millis()-lastPeak > 300UL) {
  uint32_t interval = millis()-lastPeak; lastPeak = millis();
  if (interval > 350UL && interval < 1500UL) bpmEst = 60000.0F / interval;
}
char buf[200];
snprintf(buf, sizeof(buf), "{\\"ir\\":%ld,\\"bpm_est\\":%.0f,\\"signal_ok\\":%s,\\"medical_device\\":false,\\"spo2_calibrated\\":false}", (long)irValue, bpmEst, irValue>50000L?"true":"false");
payload = String(buf);
displayLine = String("BPM~ ") + String(bpmEst,0);""",
      tests="Place a finger and confirm a plausible BPM estimate|Remove the finger and confirm signal_ok false|Verify no SpO₂ value is reported",
      fails="BPM jumps | Median-filter intervals and reject motion artefacts.|No finger detected | Increase LED current within datasheet limits.|False medical interpretation | Keep both safety flags in the payload and UI."),

    S("talking-distance-aid", "Talking Distance Aid Prototype", "Accessibility & Assistive Technology", "Intermediate",
      "esp32", ["hcsr04", "buzzer", "oled"], "serial", hours=9,
      problem="Visual-only distance displays exclude blind users; a prototype needs a distinct non-visual output pattern.",
      outcome="An ultrasonic aid maps distance bands to distinct beep rhythms, with an OLED mirror for a sighted tester.",
      objectives="Map ranges to distinguishable audio patterns|Avoid continuous alarming|Co-design with user feedback",
      use_cases="Orientation & mobility lesson|Assistive-tech prototype|Classroom accessibility demo",
      algorithm="Four distance bands produce 1-4 short beeps with a 2 s repeat; invalid echoes produce a distinct long tone.",
      logic="""int beeps = (distance_cm < 0) ? 0 : (distance_cm < 50.0F) ? 4 : (distance_cm < 100.0F) ? 3 : (distance_cm < 200.0F) ? 2 : 1;
static uint32_t lastPattern = 0;
if (millis()-lastPattern > 2000UL) {
  lastPattern = millis();
  for (int i = 0; i < beeps; i++) { digitalWrite(BUZZER_PIN, HIGH); delay(60); digitalWrite(BUZZER_PIN, LOW); delay(120); }
  if (distance_cm < 0) { digitalWrite(BUZZER_PIN, HIGH); delay(400); digitalWrite(BUZZER_PIN, LOW); }
}
char buf[150];
snprintf(buf, sizeof(buf), "{\\"distance_cm\\":%.1f,\\"beeps\\":%d,\\"visual_mirror\\":true}", distance_cm, beeps);
payload = String(buf);
displayLine = String(distance_cm,0) + " cm (" + String(beeps) + ")";""",
      tests="Place a board at 40/80/150/300 cm and count beeps|Point at open space and confirm the long error tone|Ask a tester to identify bands without looking",
      fails="Beeps hard to distinguish | Increase the gap and vary pitch, not just count.|False near alarms | Add a median filter and a minimum echo strength.|Sensor cone too wide | Add a mechanical shroud."),

    S("smart-cane-obstacle", "Smart Cane Obstacle Detector", "Accessibility & Assistive Technology", "Advanced",
      "esp32s3", ["vl53l0x", "buzzer"], "ble", hours=13, advanced=True,
      problem="A cane needs head-height obstacle detection, low latency, low weight and an explicit non-prescribed-device limitation.",
      outcome="A ToF sensor on a cane model emits a proximity buzz with BLE configuration for range and sensitivity.",
      objectives="Detect head-height obstacles|Provide BLE-configurable thresholds|Keep latency under 200 ms",
      use_cases="Mobility research|Assistive-tech course|Indoor navigation prototype",
      algorithm="A 3-frame median plus hysteresis sets the alert band; BLE characteristics allow adjusting the threshold without reflashing.",
      logic="""static float d[3] = {0,0,0}; static uint8_t i = 0;
d[i++ % 3] = distance_cm;
float med = fmaxf(fminf(d[0],d[1]), fminf(fmaxf(d[0],d[1]),d[2]));
bool near = med > 3.0F && med < 120.0F;
digitalWrite(BUZZER_PIN, near ? HIGH : LOW);
char buf[170];
snprintf(buf, sizeof(buf), "{\\"distance_cm\\":%.1f,\\"median_cm\\":%.1f,\\"alert\\":%s,\\"prescribed_device\\":false}", distance_cm, med, near?"true":"false");
payload = String(buf);""",
      tests="Walk toward a wall and confirm the buzz before 1.2 m|Change the threshold over BLE and confirm behaviour|Measure alert latency with a stopwatch",
      fails="Latency too high | Raise the sampling rate and lower the VL53L0X timing budget.|Sunlight interference | Use indoor settings or add an IR filter.|False trust in device | Keep the prescribed_device:false flag visible."),

    S("doorbell-visual-alert", "Visual Doorbell Alert for Hard-of-Hearing Users", "Accessibility & Assistive Technology", "Beginner",
      "esp32", ["sound", "ws2812b"], "wifi_mqtt", hours=7,
      problem="Audible doorbells are inaccessible to deaf and hard-of-hearing users; a visual pattern must be unmistakable.",
      outcome="A sound sensor triggers a high-contrast flashing RGB pattern and an MQTT notification for a phone.",
      objectives="Detect a doorbell-like sound without recording audio|Create an accessible visual pattern|Avoid false triggers from speech",
      use_cases="Home accessibility|Classroom demo|Shared flat",
      algorithm="A sustained sound index above a learned baseline for > 300 ms flashes the strip three times; no audio samples leave the device.",
      logic="""static float base = sound_index; static uint32_t loudAt = 0;
base = base * 0.99F + sound_index * 0.01F;
if (sound_index > base * 2.0F) { if (!loudAt) loudAt = millis(); } else loudAt = 0;
bool bell = loudAt && millis()-loudAt > 300UL && millis()-loudAt < 1500UL;
if (bell) { for (int k=0;k<3;k++) { strip.fill(strip.Color(255,255,0)); strip.show(); delay(180); strip.clear(); strip.show(); delay(180); } loudAt = 0; }
char buf[160];
snprintf(buf, sizeof(buf), "{\\"bell\\":%s,\\"audio_recorded\\":false,\\"sound_idx\\":%.1f}", bell?"true":"false", sound_index);
payload = String(buf);""",
      tests="Play a doorbell tone and confirm three flashes|Talk near the sensor and confirm no flash|Verify no audio payload is transmitted",
      fails="Speech triggers alert | Require a sustained tone and a higher ratio threshold.|Strip too dim in daylight | Increase brightness and use a diffuser.|Wi-Fi delays visual alert | Drive the strip locally before publishing."),

    S("environmental-control-switch", "Touch-Based Environmental Control Switch", "Accessibility & Assistive Technology", "Intermediate",
      "esp32", ["touch", "relay", "button"], "ble", hours=8,
      problem="Users with limited dexterity need large, low-force controls and a safe low-voltage output with feedback.",
      outcome="A capacitive touch pad toggles a low-voltage DC load with BLE status and a physical fallback button.",
      objectives="Provide a low-force touch interface|Keep a physical fallback|Report state over BLE",
      use_cases="Accessible lamp control|Assistive switch lesson|Smart home prototype",
      algorithm="Touch and button events are debounced; a state toggle drives an active-LOW relay and publishes the readback state.",
      logic="""static bool on = false; static uint32_t lastToggle = 0;
if ((touched || pressed) && millis()-lastToggle > 500UL) { on = !on; lastToggle = millis(); }
digitalWrite(RELAY_PIN, on ? LOW : HIGH);
bool actual = digitalRead(RELAY_PIN) == LOW;
char buf[150];
snprintf(buf, sizeof(buf), "{\\"on\\":%s,\\"readback\\":%s,\\"touch\\":%s,\\"button\\":%s}", on?"true":"false", actual?"true":"false", touched?"true":"false", pressed?"true":"false");
payload = String(buf);""",
      tests="Tap the pad and confirm the load toggles|Use the physical button as a fallback|Verify the BLE payload includes the GPIO readback",
      fails="Touch self-triggers | Add a ground plane and reduce sensitivity.|Relay state mismatch | Verify active-LOW wiring and readback polarity.|BLE drops | Reconnect with a bounded retry and keep local control."),

    S("ble-step-counter", "BLE Wearable Step Counter", "Wearable Electronics", "Advanced",
      "picow", ["mpu6050", "button"], "ble", hours=13, advanced=True,
      problem="Step detection from a wrist IMU is noisy; a transparent prototype should expose its heuristic nature.",
      outcome="A Pico W wearable counts step-like peaks and exposes raw magnitude, step count and a confidence note over BLE.",
      objectives="Detect step-like acceleration peaks|Reject double counts with a refractory period|Label the estimate as a heuristic",
      use_cases="Fitness prototype|Activity research|Wearable course",
      algorithm="A dynamic-threshold peak detector with a 250 ms refractory period counts steps; counts are labelled as heuristic estimates.",
      logic="""static float base = 1.0F; static uint32_t steps = 0, lastStep = 0;
base = base * 0.98F + vibration_g * 0.02F;
if (vibration_g > base * 1.25F && millis()-lastStep > 250UL) { steps++; lastStep = millis(); }
char buf[180];
snprintf(buf, sizeof(buf), "{\\"steps\\":%lu,\\"vib_g\\":%.3f,\\"base\\":%.3f,\\"method\\":\\"heuristic_peak\\",\\"accuracy_claim\\":false}", (unsigned long)steps, vibration_g, base);
payload = String(buf);""",
      tests="Walk 20 steps and compare the count|Shake the device without walking and observe false positives|Confirm the accuracy_claim:false flag",
      fails="Counts too high | Raise the refractory period and threshold ratio.|Missed slow steps | Lower the threshold and add an adaptive floor.|Battery short life | Reduce the BLE advertising rate and IMU sample rate."),

    S("wearable-air-quality-badge", "Wearable VOC Exposure Badge", "Wearable Electronics", "Advanced",
      "esp32s3", ["bme680", "oled"], "ble", hours=14, advanced=True,
      problem="Personal exposure varies by location; a badge must log gas resistance with humidity context on a small battery.",
      outcome="A wearable badge shows raw VOC trend on an OLED and streams a BLE notification with climate context.",
      objectives="Log gas resistance with temperature/humidity|Provide a local trend display|Explain burn-in and calibration limits",
      use_cases="Personal exposure study|Workshop safety research|Wearable sensor course",
      algorithm="A 10-minute rolling baseline drives a relative VOC trend arrow; raw values and climate are sent over BLE with a burn-in flag.",
      logic="""static float base = gas_kohm;
base = base * 0.99F + gas_kohm * 0.01F;
float ratio = base / fmaxf(gas_kohm, 0.01F);
const char* trend = ratio > 1.4F ? "RISING" : ratio < 0.75F ? "FALLING" : "STABLE";
char buf[220];
snprintf(buf, sizeof(buf), "{\\"gas_kohm\\":%.1f,\\"baseline\\":%.1f,\\"trend\\":\\"%s\\",\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"burn_in\\":%s}", gas_kohm, base, trend, temperature, humidity, millis()<172800000UL?"true":"false");
payload = String(buf);
displayLine = String("VOC ") + String(trend);""",
      tests="Expose to a mild vapour and confirm RISING|Verify the baseline moves slowly|Check the burn-in flag after 48 h",
      fails="Heater drains battery | Lower the heater duty cycle and sample less often.|OLED ghosting | Periodically clear the display.|Claims of IAQ accuracy | Keep the payload to raw resistance plus a trend."),

    S("smart-helmet-impact", "Smart Helmet Impact Alert", "Wearable Electronics", "Advanced",
      "esp32", ["mpu6050", "gps", "gsm"], "gsm", hours=17, advanced=True,
      problem="A lone worker who falls may be unable to call for help; an impact alert needs a location and a false-positive policy.",
      outcome="A helmet node detects a >4 g impact followed by 30 s of stillness and sends a cellular alert with coordinates.",
      objectives="Detect impact plus prolonged stillness|Geotag the emergency message|Avoid sending alerts from normal knocks",
      use_cases="Construction site research|Cycling safety prototype|Lone-worker study",
      algorithm="A 4 g threshold arms a 30 s stillness timer; if stillness persists, one geotagged alert is sent and latched until reset.",
      logic="""static uint32_t impactAt = 0; static bool sent = false;
if (vibration_g > 4.0F) impactAt = millis();
if (vibration_g > 1.3F) impactAt = 0;  // movement cancels the stillness timer
bool stillTooLong = impactAt && millis()-impactAt > 30000UL;
if (stillTooLong && !sent) {
  sent = true;
  char buf[210];
  snprintf(buf, sizeof(buf), "{\\"event\\":\\"IMPACT_ALERT\\",\\"lat\\":%.6f,\\"lng\\":%.6f,\\"peak_g\\":%.2f,\\"verified\\":false}", lat, lng, vibration_g);
  payload = String(buf);
} else payload = "";""",
      tests="Tap sharply then hold still 30 s and confirm one alert|Move continuously and confirm no alert|Verify the alert contains a valid coordinate",
      fails="False alert from dropping the helmet | Require impact plus stillness and add a 10 s cancel button.|No GPS indoors | Cache the last fix and mark location quality.|Cellular unavailable | Add a local buzzer and an optional LoRa fallback."),

    S("line-following-robot-telemetry", "Line-Following Robot with Live Telemetry", "Robotics & Automation", "Advanced",
      "esp32", ["vl53l0x", "hall", "buzzer"], "espnow", hours=15, advanced=True,
      problem="Robot tuning is slow without live state telemetry, but a USB cable constrains movement.",
      outcome="A robot streams wheel speed, obstacle distance and control state over ESP-NOW to a receiver.",
      objectives="Estimate wheel speed from hall pulses|Stream low-latency state over ESP-NOW|Add a collision-stop behaviour",
      use_cases="Mobile robot course|Control-loop tuning|Swarm robotics intro",
      algorithm="A simple proportional controller adjusts a speed setpoint; an obstacle closer than 15 cm forces a stop and a buzzer warning.",
      logic="""bool blocked = distance_cm > 2.0F && distance_cm < 15.0F;
float speed = blocked ? 0.0F : fmaxf(flow_lpm, 0.0F);
if (blocked) digitalWrite(BUZZER_PIN, HIGH); else digitalWrite(BUZZER_PIN, LOW);
char buf[180];
snprintf(buf, sizeof(buf), "R,%.2f,%.1f,%s", speed, distance_cm, blocked?"STOP":"RUN");
payload = String(buf);""",
      tests="Place an obstacle and confirm STOP state at 10 cm|Spin a wheel and confirm the speed estimate|Verify ESP-NOW latency under 100 ms",
      fails="Speed reads zero | Check the hall sensor alignment and magnet count.|Robot oscillates | Reduce the proportional gain and add a derivative term.|ESP-NOW lost packets | Match channels and shorten the antenna-to-metal distance."),

    S("plant-watering-robot", "Autonomous Plant-Watering Robot", "Robotics & Automation", "Advanced",
      "esp32s3", ["soil_cap", "hcsr04", "servo", "pump"], "wifi_mqtt", hours=20, advanced=True,
      problem="A mobile watering robot must navigate to a plant, position a nozzle and dose water without flooding.",
      outcome="A robot model approaches to 20 cm, positions a servo nozzle, waters for 3 s and reports soil moisture before/after.",
      objectives="Fuse distance and soil moisture for a dosing decision|Sequence motion and actuation safely|Log before/after measurements",
      use_cases="Greenhouse robot research|Robotics capstone|Precision watering study",
      algorithm="A state machine (SEEK, POSITION, WATER, RETREAT) gates the pump; water is allowed only within a distance window and a dry-soil condition.",
      logic="""static const char* state = "SEEK";
if (strcmp(state,"SEEK")==0 && distance_cm > 15.0F && distance_cm < 25.0F) state = "POSITION";
if (strcmp(state,"POSITION")==0) { actuator.write(45); state = "WATER"; }
if (strcmp(state,"WATER")==0 && soil_pct < 30.0F) { digitalWrite(PUMP_PIN, HIGH); delay(3000); digitalWrite(PUMP_PIN, LOW); state = "RETREAT"; }
if (strcmp(state,"RETREAT")==0) { actuator.write(0); state = "SEEK"; }
char buf[220];
snprintf(buf, sizeof(buf), "{\\"state\\":\\"%s\\",\\"soil_pct\\":%.1f,\\"distance_cm\\":%.1f,\\"pump\\":false}", state, soil_pct, distance_cm);
payload = String(buf);""",
      tests="Place a dry plant at 20 cm and confirm a 3 s dose|Test with wet soil and confirm no water|Confirm the pump is OFF in SEEK and RETREAT",
      fails="Pump floods | Shorten the burst and add a flow sensor for feedback.|Servo collides with plants | Add mechanical stops and limit angles.|Robot drives into obstacles | Add a second distance sensor for the rear."),

    S("robotic-gripper-force", "Robotic Gripper with Force Feedback", "Robotics & Automation", "Advanced",
      "esp32", ["hx711", "servo", "oled"], "serial", hours=13, advanced=True,
      problem="A position-controlled gripper crushes fragile items; force feedback needs a load cell and a controlled approach.",
      outcome="A gripper closes until a target force is reached, holds it, and displays measured grams on an OLED.",
      objectives="Calibrate a load cell with a known mass|Implement a force-limited close loop|Detect slip from a sudden force drop",
      use_cases="Soft-fruit handling lab|Robotics course|Force-control research",
      algorithm="The servo advances in 2° steps until weight_g exceeds 150 g; a > 30 % drop within one cycle flags slip.",
      logic="""static int angle = 0; static float lastForce = 0;
if (fabsf(weight_g) < 150.0F) angle = min(angle + 2, 90);
actuator.write(angle);
bool slip = (lastForce > 100.0F && fabsf(weight_g) < lastForce * 0.7F);
lastForce = fabsf(weight_g);
char buf[180];
snprintf(buf, sizeof(buf), "{\\"grams\\":%.1f,\\"angle_deg\\":%d,\\"slip\\":%s}", weight_g, angle, slip?"true":"false");
payload = String(buf);
displayLine = String(weight_g,0) + " g @" + String(angle) + "deg";""",
      tests="Tare with no load then calibrate with a 200 g mass|Grip a soft object and confirm the force limit|Remove the object and confirm slip detection",
      fails="Force oscillates | Reduce the step size and add a low-pass filter.|HX711 noisy | Shield the wires and keep them away from servo cables.|Load cell overload | Add a mechanical stop and never exceed the rated load."),

    S("warehouse-line-follower", "Warehouse Line-Follower with Dead Reckoning", "Robotics & Automation", "Advanced",
      "esp32", ["mpu6050", "vl53l0x", "ethernet"], "ethernet", hours=18, advanced=True,
      problem="Indoor robots cannot rely on GPS; fused IMU/ToF dead reckoning needs explicit drift disclosure.",
      outcome="A robot estimates relative position from acceleration and ToF landmarks, publishing position with a drift warning.",
      objectives="Fuse IMU and range data for a relative pose|Quantify drift honestly|Stream pose over wired Ethernet",
      use_cases="Warehouse robot research|Indoor navigation course|Sensor fusion lab",
      algorithm="Double-integrated acceleration is corrected by ToF wall distance; a growing covariance proxy warns when the pose is unreliable.",
      logic="""static float x = 0, vx = 0, cov = 0;
vx = vx * 0.98F + ax * 0.005F; x += vx * 0.005F; cov += 0.002F;
if (distance_cm > 5.0F && distance_cm < 200.0F) { x = 200.0F - distance_cm; cov = 0.0F; }
char buf[210];
snprintf(buf, sizeof(buf), "{\\"x_cm\\":%.1f,\\"wall_cm\\":%.1f,\\"drift\\":%.2f,\\"pose_reliable\\":%s}", x, distance_cm, cov, cov<1.0F?"true":"false");
payload = String(buf);""",
      tests="Move the robot 50 cm and compare x_cm with a ruler|Block the ToF sensor and confirm drift rises|Recover a landmark and confirm the pose resets",
      fails="Pose drifts quickly | Fuse wheel odometry and recalibrate IMU bias.|Ethernet cable drags | Use a drag chain or switch to Wi-Fi 6 / ESP-NOW.|Vibration saturates IMU | Damp the mount and reduce the acceleration range."),
]
