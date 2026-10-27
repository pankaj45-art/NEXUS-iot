"""Pro library part D: edge AI, low power, security, campus, remote, custom."""
from .spec_base import S

SPECS = [
    S("keyword-spotting-front-end", "Edge AI Keyword-Spotting Front End", "Edge AI & Sensor Fusion", "Advanced",
      "esp32s3", ["mic_i2s", "sdcard"], "serial", hours=22, advanced=True,
      problem="Always-on keyword spotting needs a clean I2S audio front end before any model is trained or deployed.",
      outcome="An ESP32-S3 captures 16 kHz mono audio frames, computes windowed RMS energy and logs labelled frames for dataset collection.",
      objectives="Configure I2S for a 24-bit MEMS microphone|Compute a windowed feature without an ML framework|Label and store frames for later training",
      use_cases="Keyword dataset collection|Edge ML course|Acoustic event research",
      algorithm="A 512-sample window yields RMS and zero-crossing rate; a simple energy gate marks speech-like frames and saves them with a label file.",
      logic="""static uint32_t frames = 0; frames++;
bool speechLike = rms > 120.0F;
char buf[200];
snprintf(buf, sizeof(buf), "%lu,%.2f,%s,%s", (unsigned long)frames, rms, speechLike?"SPEECH":"SILENCE", "label=unknown");
payload = String(buf); logLine = payload;
if (speechLike) Serial.println(F("[INFO] Frame tagged for labelling"));""",
      tests="Speak near the mic and confirm RMS rises|Record 100 frames and verify the CSV parses|Compare RMS with a known 1 kHz tone at fixed distance",
      fails="Samples all zero | Verify I2S WS/SD/SCK wiring and 24-bit word alignment.|DC offset dominates | Subtract the running mean before computing RMS.|SD write too slow | Buffer a full sector before writing."),

    S("camera-occupancy-counter", "Privacy-Preserving Camera Occupancy Counter", "Edge AI & Sensor Fusion", "Advanced",
      "rpi4", ["camera"], "wifi_http", hours=24, advanced=True,
      problem="Camera people-counting must avoid storing identifiable images while still giving useful occupancy numbers.",
      outcome="A Raspberry Pi processes frames locally and posts only an anonymous count, never an image, with an explicit processing-status flag.",
      objectives="Capture frames locally on a Linux host|Discard frames immediately after inference|Publish only aggregate counts and confidence",
      use_cases="Library occupancy|Meeting-room display|Privacy-first sensing research",
      algorithm="A background-subtraction blob counter estimates occupancy; frames are released from memory before any network call; counts are smoothed over 10 frames.",
      logic="""# Python inference pipeline generated in the Python firmware section.
payload = "{\\"occupancy\\":0,\\"privacy\\":\\"frames_never_stored\\",\\"model\\":\\"blob_heuristic\\"}";""",
      tests="Walk two people through the frame and confirm a count of ~2|Verify no image files are written to disk|Confirm the count is smoothed over 10 frames",
      fails="Lighting changes break background model | Use adaptive background updates and an IR illuminator.|Privacy leak from logs | Never log frame buffers or base64 image data.|CPU too slow | Reduce resolution and use a lightweight motion ROI."),

    S("multisensor-anomaly-fusion", "Multi-Sensor Anomaly Fusion Node", "Edge AI & Sensor Fusion", "Advanced",
      "esp32s3", ["mpu6050", "sound", "ina219"], "wifi_mqtt", hours=20, advanced=True,
      problem="Single-sensor anomaly detectors produce false alarms; fusion needs a transparent, trainable feature vector.",
      outcome="An ESP32-S3 publishes a fused feature vector and an interpretable z-score anomaly flag rather than an opaque model output.",
      objectives="Build a synchronous feature vector from three sensors|Compute per-feature z-scores online|Log features for offline model training",
      use_cases="Equipment health dataset|Sensor-fusion research|Explainable edge AI course",
      algorithm="Vibration, sound and power features are normalised with Welford running mean/variance; two features above 3σ raise an anomaly flag.",
      logic="""static float meanV=0,varV=0,meanS=0,varS=0,meanP=0,varP=0; static uint32_t n=1;
float zv = (vibration_g-meanV)/sqrtf(varV/n+0.01F);
float zs = (sound_index-meanS)/sqrtf(varS/n+0.01F);
float zp = (power_w-meanP)/sqrtf(varP/n+0.01F);
meanV += (vibration_g-meanV)/n; varV += powf(vibration_g-meanV,2); n++;
uint8_t flags = (fabsf(zv)>3.0F) + (fabsf(zs)>3.0F) + (fabsf(zp)>3.0F);
char buf[240];
snprintf(buf, sizeof(buf), "{\\"vib_g\\":%.3f,\\"sound\\":%.1f,\\"power_w\\":%.2f,\\"z_vib\\":%.2f,\\"z_sound\\":%.2f,\\"z_power\\":%.2f,\\"anomaly\\":%s}", vibration_g, sound_index, power_w, zv, zs, zp, flags>=2?"true":"false");
payload = String(buf);""",
      tests="Inject a vibration spike and confirm the z-score rises|Verify an anomaly needs two flagged features|Log 1000 rows and confirm the CSV is model-ready",
      fails="Z-scores unstable at startup | Seed the running stats over the first 100 samples.|Features out of sync | Sample all sensors in one loop iteration.|Numerical overflow | Clamp inputs and use a bounded window."),

    S("tinyml-vibration-classifier", "TinyML Vibration Classifier Prototype", "Edge AI & Sensor Fusion", "Advanced",
      "esp32", ["mpu6050", "sdcard", "buzzer"], "serial", hours=24, advanced=True,
      problem="Deploying a classifier without labelled data and an honest evaluation produces impressive but useless demos.",
      outcome="A prototype collects labelled vibration windows, computes FFT-like band energies and reports a rule-based baseline accuracy target.",
      objectives="Collect labelled windows for two machine states|Extract band-energy features|Report a confusion matrix, not just accuracy",
      use_cases="Predictive-maintenance course|TinyML dataset builder|Edge ML benchmarking",
      algorithm="A 64-sample window's energy in three frequency bands forms a feature vector; a nearest-centroid classifier is evaluated against held-out labels.",
      logic="""static float e[3] = {0,0,0};
e[0] = e[0]*0.9F + vibration_g*0.1F;
e[1] = e[1]*0.7F + vibration_g*0.3F;
e[2] = vibration_g;
const char* cls = (e[2] > 1.8F) ? "ABNORMAL" : "NORMAL";
char buf[220];
snprintf(buf, sizeof(buf), "%.4f,%.4f,%.4f,%s,label=unknown", e[0], e[1], e[2], cls);
payload = String(buf); logLine = payload;
if (strcmp(cls,"ABNORMAL")==0) digitalWrite(BUZZER_PIN, HIGH); else digitalWrite(BUZZER_PIN, LOW);""",
      tests="Collect 100 NORMAL and 100 ABNORMAL labelled windows|Compute a confusion matrix offline|Confirm the buzzer follows the classifier output",
      fails="No real FFT | This is a filter-bank approximation; state that clearly before claiming ML results.|Labels missing | Provide a button-driven label input during collection.|Class imbalance | Collect equal windows per state."),

    S("deep-sleep-soil-node", "Deep-Sleep Soil Moisture Node", "Low-Power Sensor Networks", "Advanced",
      "esp32", ["soil_cap", "lora"], "lora", hours=16, advanced=True,
      problem="Battery-powered field sensors must sample rarely and power-gate their probes to avoid corrosion and drain.",
      outcome="A node wakes every 30 minutes, powers the capacitive probe for 2 s, sends one LoRa frame and returns to deep sleep.",
      objectives="Power-gate an analog sensor with a MOSFET|Use ESP32 deep sleep with a timer wakeup|Measure real sleep current",
      use_cases="Orchard soil monitoring|Research plot|Battery-life experiment",
      algorithm="RTC memory holds a boot counter; the probe is energised only in the awake window; the frame includes battery voltage and a sample sequence.",
      logic="""static uint32_t seq = 0; seq++;
char buf[120];
snprintf(buf, sizeof(buf), "D,%lu,%.1f,%.2f", (unsigned long)seq, soil_pct, (float)analogRead(34)/4095.0F*3.3F*2.0F);
payload = String(buf);
Serial.println(F("[INFO] Sample sent; scheduler will enter deep sleep now"));""",
      tests="Measure awake and sleep current with a power profiler|Confirm a 30-minute wake interval over 4 hours|Verify the probe is unpowered during sleep",
      fails="Sleep current too high | Disconnect the USB-UART bridge and power-gate all sensors.|LoRa TX brownout | Add a 470 µF capacitor near the radio.|Probe drift | Keep excitation brief and recalibrate seasonally."),

    S("espnow-battery-mesh", "ESP-NOW Battery Sensor Mesh", "Low-Power Sensor Networks", "Intermediate",
      "picow", ["bme280"], "espnow", hours=13,
      problem="A mesh of battery sensors needs collision avoidance and stale-node detection without a Wi-Fi router.",
      outcome="Pico W leaf nodes send staggered BME280 readings over ESP-NOW with a sequence number and battery hint.",
      objectives="Stagger transmissions to avoid collisions|Detect stale nodes at the receiver|Report battery proxy with each sample",
      use_cases="Greenhouse sensor mesh|Building monitoring|Low-power wireless course",
      algorithm="Each node derives a send slot from its chip ID; the receiver marks a node stale after 3 missed intervals.",
      logic="""static uint32_t seq = 0; seq++;
uint32_t nodeId = (uint32_t)(rp2040.getChipID() & 0xFFFF);
if ((millis() / 1000UL) % 6UL == nodeId % 6UL) {
  char buf[180];
  snprintf(buf, sizeof(buf), "{\\"node\\":%lu,\\"seq\\":%lu,\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"p_hpa\\":%.1f}", (unsigned long)nodeId, (unsigned long)seq, temperature, humidity, pressure);
  payload = String(buf);
} else payload = "";""",
      tests="Power three nodes and confirm all IDs at the receiver|Switch one off and confirm stale detection|Measure average current per node",
      fails="ESP-NOW unsupported on Pico W | Use the documented arduino-pico ESP-NOW API or switch to an ESP32 leaf.|Collisions | Increase the number of slots and jitter the wake time.|Battery estimate missing | Add a divider on an ADC pin for VSYS."),

    S("nb-iot-remote-telemetry", "Cellular Remote Telemetry with Store-and-Forward", "Low-Power Sensor Networks", "Advanced",
      "esp32", ["bme280", "gsm", "rtc", "sdcard"], "gsm", hours=20, advanced=True,
      problem="Remote telemetry loses data during cellular outages; store-and-forward must be bounded and verifiable.",
      outcome="A node buffers time-stamped climate rows to SD during outages and flushes them in batches when the modem reconnects.",
      objectives="Implement a bounded circular buffer on SD|Retry modem registration with backoff|Verify flushed rows are acknowledged",
      use_cases="Remote weather site|Pipeline monitoring|Off-grid research",
      algorithm="A send queue pointer in RTC memory advances only on HTTP 2xx; a maximum queue size prevents unbounded SD growth.",
      logic="""static uint32_t queued = 0;
bool networkOk = modem.isNetworkConnected();
if (!networkOk) queued++;
char buf[220];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"p_hpa\\":%.1f,\\"queued\\":%lu,\\"network\\":%s}", timestamp, temperature, humidity, pressure, (unsigned long)queued, networkOk?"true":"false");
payload = String(buf); logLine = payload;""",
      tests="Disconnect the antenna and confirm rows queue to SD|Reconnect and confirm a batch flush|Fill the queue cap and confirm an overflow warning",
      fails="Modem never registers | Check the APN, SIM activation and supported bands.|SD file grows unbounded | Enforce the queue cap and rotate log files.|Duplicate uploads | Advance the queue pointer only after a 2xx response."),

    S("battery-health-lora", "LoRa Node Battery Health Forecaster", "Low-Power Sensor Networks", "Advanced",
      "esp32", ["ina219", "lora", "rtc"], "lora", hours=15, advanced=True,
      problem="Field nodes fail unexpectedly; a simple voltage-only battery gauge is inaccurate under pulsed radio loads.",
      outcome="A node estimates remaining battery life from coulomb counting and voltage sag during LoRa transmissions.",
      objectives="Measure voltage sag synchronised with TX|Accumulate charge with a real battery capacity|Forecast days remaining with stated uncertainty",
      use_cases="Remote sensor fleet|Solar node maintenance|Power-profiling study",
      algorithm="Charge is integrated from measured current; a TX-time sag below 3.3 V flags an ageing cell; days remaining is a linear projection with a ±30 % caveat.",
      logic="""static float soc = 100.0F;
soc -= (fabsf(current_ma) / 1000.0F) * (SAMPLE_INTERVAL_MS/3600000.0F) / BATTERY_AH * 100.0F;
float days = fmaxf(soc,0.0F) / fmaxf(fabsf(current_ma)/1000.0F*24.0F, 0.01F);
char buf[160];
snprintf(buf, sizeof(buf), "H,%.2f,%.0f,%.0f,%.1f", voltage_v, current_ma, soc, days);
payload = String(buf);""",
      tests="Draw a known 100 mA load for 1 h and compare SoC drop|Measure sag during LoRa TX|Verify the forecast carries the ±30 % caveat in documentation",
      fails="SoC drift | Reset to 100 % at a measured full charge and compensate temperature.|Sag masked by regulator | Measure at the cell, upstream of the boost converter.|INA219 range exceeded | Use the correct shunt and bus voltage limits."),

    S("secure-device-health", "Secure Boot and Device Health Dashboard", "IoT Security & Device Diagnostics", "Advanced",
      "esp32s3", ["rtc", "oled"], "wifi_mqtt", hours=18, advanced=True,
      problem="Field devices need verifiable boot integrity and a health channel that does not leak secrets.",
      outcome="A node reports a boot count, firmware version hash placeholder, free heap and uptime with a secure-boot status flag.",
      objectives="Report firmware identity without embedding keys|Expose heap/uptime diagnostics|Explain secure-boot verification steps",
      use_cases="Fleet monitoring|Security course|Diagnostics baseline",
      algorithm="A health message is built from ESP-IDF APIs (heap, uptime) plus a compile-time version string; no secrets are included.",
      logic="""char buf[240];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"uptime_s\\":%lu,\\"free_heap\\":%lu,\\"fw\\":\\"YOUR_FW_VERSION\\",\\"secure_boot\\":\\"VERIFY_IN_IDF_MENUCONFIG\\"}", timestamp, (unsigned long)(millis()/1000UL), (unsigned long)ESP.getFreeHeap());
payload = String(buf);
displayLine = String("Up ") + String(millis()/1000UL) + "s";""",
      tests="Confirm the health topic contains no credentials|Reboot and confirm uptime resets and boot count increments|Document the secure-boot enablement procedure",
      fails="Heap leak over 24 h | Diff free_heap hourly and review String allocations.|Secure boot not actually enabled | Follow the ESP-IDF menuconfig procedure and verify eFuses.|Clock wrong | Sync with NTP and fall back to the RTC."),

    S("mqtt-tls-rotation", "MQTT TLS Credential Rotation Monitor", "IoT Security & Device Diagnostics", "Advanced",
      "esp32", ["rtc", "sdcard"], "wifi_mqtt", hours=19, advanced=True,
      problem="Long-lived device credentials are a common IoT weakness; rotation needs an auditable, offline-safe process.",
      outcome="A monitor tracks credential age, warns 14 days before expiry and logs rotation events without storing secrets on SD.",
      objectives="Track credential age from an RTC date|Warn before expiry|Keep secrets out of logs and examples",
      use_cases="Fleet security exercise|MQTT hardening lab|Credential-lifecycle demo",
      algorithm="A configured expiry date is compared with the RTC date; warnings escalate at 14 and 3 days; rotation events are logged with only a fingerprint.",
      logic="""int daysLeft = (int)(CRED_EXPIRY_EPOCH - rtcEpochPlaceholder);  // TODO: implement RTC->epoch conversion
const char* state = daysLeft < 0 ? "EXPIRED" : daysLeft < 3 ? "CRITICAL" : daysLeft < 14 ? "ROTATE_SOON" : "OK";
char buf[200];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"credential_days_left\\":%d,\\"state\\":\\"%s\\",\\"secret_in_log\\":false}", timestamp, daysLeft, state);
payload = String(buf); logLine = payload;""",
      tests="Set the RTC past expiry and confirm EXPIRED|Set 10 days left and confirm ROTATE_SOON|Grep the log and confirm no credential material is stored",
      fails="TLS handshake fails | Install the correct root CA and use WiFiClientSecure.|RTC epoch conversion missing | Use mktime() with the DS3231 DateTime fields.|ACL not updated on rotation | Automate broker ACL updates with the rotation job."),

    S("tamper-detection-node", "Tamper Detection and Secure Enclosure Node", "IoT Security & Device Diagnostics", "Advanced",
      "esp32", ["reed", "mpu6050", "gsm"], "gsm", hours=17, advanced=True,
      problem="Outdoor IoT enclosures can be opened or moved; a security node must detect and report tamper events with a heartbeat.",
      outcome="A node latches a tamper flag from a case-open contact or >1.5 g motion, sends one cellular alert and then a 10-minute heartbeat.",
      objectives="Detect case opening with a reed contact|Detect movement with an IMU|Send an authenticated cellular tamper alert",
      use_cases="Remote cabinet|Utility meter enclosure|Security research",
      algorithm="A case-open signal or a > 1.5 g movement event latches a tamper flag; a cellular alert is sent once, followed by a 10-minute heartbeat.",
      logic="""static bool tamper = false; static uint32_t lastAlert = 0;
if (door_open || vibration_g > 1.5F) tamper = true;
if (tamper && millis()-lastAlert > 600000UL) {
  lastAlert = millis();
  char buf[180];
  snprintf(buf, sizeof(buf), "{\\"tamper\\":true,\\"case_open\\":%s,\\"vib_g\\":%.2f,\\"authenticated\\":\\"HMAC_TODO\\"}", door_open?"true":"false", vibration_g);
  payload = String(buf);
} else payload = "";""",
      tests="Open the reed contact and confirm a tamper alert|Shake the enclosure and confirm motion detection|Verify the heartbeat continues after the first alert",
      fails="False tamper from vibration | Require two events within 5 s and add a threshold.|Alert can be spoofed | Add an HMAC with a device-unique key in secure storage.|Cellular offline | Buffer the event and retry with backoff."),

    S("ota-rollback-monitor", "Firmware OTA Rollback Monitor", "IoT Security & Device Diagnostics", "Advanced",
      "esp32", ["sdcard", "oled"], "wifi_http", hours=18, advanced=True,
      problem="A failed OTA update can brick a fleet; devices need a watchdog and a documented rollback procedure.",
      outcome="A node reports its active partition, boot count and a rollback status derived from a validated boot marker.",
      objectives="Track consecutive failed boots|Validate a firmware image before marking it good|Expose rollback status remotely",
      use_cases="Fleet OTA research|Firmware reliability lab|Secure update course",
      algorithm="A boot marker in NVS is only marked 'valid' after the app checks in; failed boots increment a counter that triggers rollback.",
      logic="""char buf[220];
snprintf(buf, sizeof(buf), "{\\"fw\\":\\"YOUR_FW_VERSION\\",\\"boot_count\\":%lu,\\"uptime_s\\":%lu,\\"rollback\\":\\"WATCHDOG_POLICY\\",\\"signed\\":\\"VERIFY_IN_IDF\\"}", (unsigned long)bootCounterPlaceholder, (unsigned long)(millis()/1000UL));
payload = String(buf); logLine = payload;
displayLine = String("FW ") + String("YOUR_FW_VERSION");""",
      tests="Simulate three failed boots and confirm rollback status|Confirm a successful check-in clears the counter|Verify no unsigned image is accepted in the documented procedure",
      fails="Boot loop after OTA | Keep the factory partition and enable the ESP-IDF rollback feature.|Signature not checked | Enable secure boot and signed OTA verification.|Logs leak keys | Redact all secret fields before writing to SD."),

    S("classroom-co2-occupancy", "Classroom CO₂ and Occupancy Monitor", "Smart Campus Systems", "Intermediate",
      "esp32", ["scd30", "pir", "oled"], "wifi_mqtt", hours=10,
      problem="Classroom ventilation decisions need both occupancy and CO₂; one signal alone is misleading.",
      outcome="A node reports estimated occupancy state, NDIR CO₂ and a ventilation recommendation with an evidence trail.",
      objectives="Combine motion and CO₂ contextually|Report an auditable recommendation rule|Preserve anonymity",
      use_cases="School classroom|Lecture hall|Campus sustainability study",
      algorithm="Ventilation is recommended when CO₂ > 1000 ppm with recent occupancy, or > 1400 ppm regardless; all rules are published with the message.",
      logic="""static uint32_t lastMotion = 0;
if (motion) lastMotion = millis();
bool recentlyOccupied = millis()-lastMotion < 600000UL;
const char* rec = (co2 > 1400.0F || (co2 > 1000.0F && recentlyOccupied)) ? "VENTILATE" : "OK";
char buf[230];
snprintf(buf, sizeof(buf), "{\\"co2_ppm\\":%.0f,\\"occupancy_recent\\":%s,\\"recommendation\\":\\"%s\\",\\"rule\\":\\"co2_gt_1000_and_occupied\\",\\"anonymous\\":true}", co2, recentlyOccupied?"true":"false", rec);
payload = String(buf);
displayLine = String(co2,0) + " ppm " + String(rec);""",
      tests="Exhale near the sensor with motion and confirm VENTILATE|Confirm no personal data in the payload|Verify the rule string matches the implemented logic",
      fails="PIR cannot cover the room | Use multiple sensors or a mmWave presence detector.|CO₂ sensor drift | Enable ASC in a room that reaches fresh air nightly.|Recommendation ignored | Log the rule and show it on the dashboard."),

    S("campus-bike-rack", "Campus Bike Rack Occupancy Monitor", "Smart Campus Systems", "Advanced",
      "esp32", ["reed", "lora"], "lora", hours=14, advanced=True,
      problem="Outdoor bike racks need long-range, low-power occupancy sensing without cameras.",
      outcome="A LoRa node reports the number of occupied rack slots using reed contacts and a heartbeat.",
      objectives="Monitor multiple reed switches with a shared bus|Debounce mechanical contacts|Report a compact occupancy bitmask",
      use_cases="Campus bike parking|Secure cycle store|Facilities planning",
      algorithm="Each contact maps to one bit in an 8-bit mask; a 500 ms debounce and a 15-minute heartbeat keep airtime low.",
      logic="""uint8_t mask = 0;
if (door_open) mask |= 0x01;   // slot 1 shown; expand with a multiplexer for 8 slots
static uint8_t lastMask = 0xFF;
if (mask != lastMask) { lastMask = mask; char buf[80]; snprintf(buf, sizeof(buf), "K,%u,%s", mask, "CHANGE"); payload = String(buf); }
else { static uint32_t hb=0; if (millis()-hb > 900000UL) { hb=millis(); char buf[80]; snprintf(buf,sizeof(buf),"K,%u,%s",mask,"HB"); payload=String(buf); } else payload=""; }""",
      tests="Close/open the contact and confirm a change frame|Confirm a 15-minute heartbeat|Measure sleep current with a multimeter",
      fails="Contacts bounce | Add 100 nF capacitors and a longer debounce.|LoRa range blocked by metal racks | Move the antenna above the rack.|Wrong slot mapping | Document the bit order on the enclosure."),

    S("library-noise-monitor", "Library Quiet-Zone Noise Monitor", "Smart Campus Systems", "Intermediate",
      "esp32", ["sound", "oled"], "wifi_http", hours=9,
      problem="Quiet zones need a non-punitive nudge; a monitor should show trends, not record conversations.",
      outcome="A node shows a rolling noise-level indicator on an OLED and posts only aggregate indices, never audio.",
      objectives="Aggregate sound samples locally|Display a colour-free, readable level|Respect privacy by never storing audio",
      use_cases="Library study area|Open-plan office|Classroom acoustics",
      algorithm="A 10-second rolling average and peak index feed a three-level indicator; only numeric aggregates leave the device.",
      logic="""static float avg = sound_index;
avg = avg * 0.9F + sound_index * 0.1F;
const char* level = avg > 70.0F ? "LOUD" : avg > 45.0F ? "MODERATE" : "QUIET";
char buf[180];
snprintf(buf, sizeof(buf), "{\\"sound_idx\\":%.1f,\\"avg_idx\\":%.1f,\\"level\\":\\"%s\\",\\"audio_stored\\":false}", sound_index, avg, level);
payload = String(buf);
displayLine = String("Noise ") + String(level) + " " + String(avg,0);""",
      tests="Clap repeatedly and confirm LOUD|Verify no audio payload or file is produced|Confirm the 10 s average smoothing",
      fails="Ambient HVAC biases readings | Measure a baseline and subtract it.|Display distracting | Use a dim, slow-refresh indicator.|Privacy concerns | Keep the aggregate-only policy visible in the UI."),

    S("campus-energy-dashboard", "Campus Energy Dashboard Aggregator", "Smart Campus Systems", "Advanced",
      "rpi4", ["ina219", "rs485", "ethernet"], "ethernet", hours=20, advanced=True,
      problem="Campus energy dashboards mix low-voltage DC test circuits and Modbus meters; units and sources must be explicit.",
      objectives="Label each measurement source and unit|Poll Modbus and I2C sensors in one service|Expose data-quality flags",
      use_cases="Campus sustainability dashboard|Building sub-metering|Energy data course",
      outcome="A Raspberry Pi aggregates INA219 DC measurements and Modbus registers into one labelled MQTT stream with source flags.",
      algorithm="A Python scheduler reads both interfaces, tags each value with source and unit, and publishes a merged document with a freshness flag.",
      logic="""# Python aggregation logic generated in the Python firmware section.
payload = "{\\"sources\\":[\\"ina219_dc\\",\\"modbus_rtu\\"],\\"units\\":\\"SI\\",\\"freshness\\":\\"flagged\\"}";""",
      tests="Publish a known DC load and confirm the INA219 value|Simulate a Modbus register and confirm the merged payload|Stop one source and confirm a staleness flag",
      fails="Unit mismatch (mA vs A) | Normalise all values to SI units at ingestion.|RS-485 timeout blocks loop | Use a short timeout and a separate thread|SD card wear | Use a log rotation policy."),

    S("remote-cabin-monitor", "Remote Cabin Temperature and Leak Monitor", "Remote Monitoring", "Advanced",
      "esp32", ["bme280", "water_leak", "gsm"], "gsm", hours=15, advanced=True,
      problem="Unattended cabins can freeze or flood; cellular telemetry and a low-temperature alert are essential.",
      outcome="A node sends climate and leak status hourly with an immediate freeze-risk alert below 3 °C.",
      objectives="Combine climate and leak sensing|Send immediate alerts with hourly heartbeats|Handle cellular outages",
      use_cases="Holiday cabin|Remote storage|Mountain hut",
      algorithm="A freeze or leak event overrides the hourly schedule; a message counter is used to detect missed reports at the server.",
      logic="""static uint32_t lastSend = 0, seq = 0;
bool leak = leak_pct > 40.0F;
bool freeze = temperature < 3.0F;
if (leak || freeze || millis()-lastSend > 3600000UL) {
  lastSend = millis(); seq++;
  char buf[230];
  snprintf(buf, sizeof(buf), "{\\"seq\\":%lu,\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"p_hpa\\":%.1f,\\"leak_pct\\":%.1f,\\"freeze_risk\\":%s,\\"leak\\":%s}", (unsigned long)seq, temperature, humidity, pressure, leak_pct, freeze?"true":"false", leak?"true":"false");
  payload = String(buf);
} else payload = "";""",
      tests="Cool the BME280 below 3 °C and confirm an immediate alert|Wet the leak rope and confirm a leak message|Verify hourly heartbeats with sequence continuity",
      fails="Cellular coverage absent | Add an external antenna or a LoRa fallback gateway.|Leak rope false positive | Use a guarded sensing cable and a higher threshold.|Message gaps | Check the sequence number at the server and buffer locally."),

    S("offgrid-borehole-monitor", "Off-Grid Borehole Level Monitor", "Remote Monitoring", "Advanced",
      "esp32", ["water_level", "lora", "rtc"], "lora", hours=17, advanced=True,
      problem="Boreholes are often far from power and connectivity; a monitor needs a pressure/level sensor and long-range radio.",
      outcome="A solar LoRa node reports borehole level percentage and a 24-hour trend with a pump-protection warning.",
      objectives="Calibrate a level sensor for a deep borehole|Compute a 24-hour trend|Warn before dry-running a pump",
      use_cases="Farm water supply|Remote well|Groundwater study",
      algorithm="A 12-point running trend estimates level change per hour; a drop below 20 % raises a pump-protection warning.",
      logic="""static float hist[12] = {0}; static uint8_t n = 0;
hist[n++ % 12] = level_pct;
float trend = (n >= 12) ? (hist[(n-1)%12] - hist[n%12]) : 0.0F;
char buf[160];
snprintf(buf, sizeof(buf), "W,%.1f,%.2f,%s", level_pct, trend, level_pct < 20.0F ? "PUMP_PROTECT":"OK");
payload = String(buf);""",
      tests="Change the sensor level and confirm percentage tracking|Feed a falling trend and confirm PUMP_PROTECT|Verify RTC timestamps on the gateway",
      fails="Level sensor fouls | Use a vented pressure transducer with a protective cage.|LoRa link marginal | Use a higher-gain antenna and a clear line of sight.|Solar undersized | Size the panel for the worst winter month."),

    S("generator-fuel-monitor", "Remote Generator Fuel Level Monitor", "Remote Monitoring", "Advanced",
      "esp32", ["hcsr04", "gps", "gsm"], "gsm", hours=16, advanced=True,
      problem="Backup generators run out of fuel during outages; a monitor needs level, location and low-fuel alerting.",
      outcome="A cellular node converts ultrasonic distance into fuel litres with a tank geometry constant and a geotagged low-fuel alert.",
      objectives="Convert distance to volume for a real tank|Geotag the installation|Alert below a configurable reserve",
      use_cases="Telecom backup generator|Construction site generator|Remote cabin power",
      algorithm="Fuel height is derived from a measured tank height; litres use a documented rectangular/cylindrical approximation with an uncertainty note.",
      logic="""float fuel_cm = FUEL_TANK_HEIGHT_CM - distance_cm;
float litres = fmaxf(fuel_cm,0.0F) * FUEL_TANK_AREA_CM2 / 1000.0F;
bool low = litres < 15.0F;
char buf[220];
snprintf(buf, sizeof(buf), "{\\"lat\\":%.6f,\\"lng\\":%.6f,\\"fuel_l\\":%.1f,\\"low_fuel\\":%s,\\"geometry\\":\\"approximate\\"}", lat, lng, litres, low?"true":"false");
payload = String(buf);""",
      tests="Set a known distance and verify litres against manual calculation|Trigger low fuel and confirm an alert|Verify the coordinates match the installation",
      fails="Fuel vapour damages electronics | Use a sealed, rated sensor and keep electronics outside the tank.|Foam/slosh gives spikes | Median-filter over 10 samples and sample with the generator off.|Ultrasonic fails in vapour | Use a capacitive or pressure-based level probe."),

    S("satellite-ready-asset-beacon", "Hybrid Cellular Asset Beacon", "Remote Monitoring", "Advanced",
      "esp32", ["gps", "gsm", "rtc", "sdcard"], "gsm", hours=22, advanced=True,
      problem="Assets travel beyond cellular coverage; a beacon must queue positions and clearly disclose that satellite is NOT included.",
      outcome="A tracker buffers geotagged positions to SD when cellular is unavailable and uploads them in order when coverage returns.",
      objectives="Implement an ordered upload queue|Detect coverage gaps|Document that a satellite modem is a future upgrade",
      use_cases="Remote asset tracking|Field research equipment|Logistics audit",
      algorithm="Each fix is appended with a sequence number and RTC time; a send pointer advances only on confirmed upload; no satellite hardware is claimed.",
      logic="""static uint32_t seq = 0; seq++;
char buf[230];
snprintf(buf, sizeof(buf), "%lu,%s,%.6f,%.6f,%s", (unsigned long)seq, timestamp, lat, lng, modem.isNetworkConnected()?"LIVE":"QUEUED");
payload = String(buf); logLine = payload;""",
      tests="Disable the antenna and confirm QUEUED rows on SD|Restore coverage and confirm ordered upload|Verify no satellite capability is claimed",
      fails="Queue grows unbounded | Cap the queue and drop the oldest with a counter.|Time drift while offline | Use the RTC and re-sync on reconnect.|Power loss during write | Flush each row and use a supercapacitor."),

    S("mountain-weather-relay", "Mountain Weather Relay with Store-and-Forward", "Remote Monitoring", "Advanced",
      "esp32", ["bme280", "lora", "gps", "sdcard"], "lora", hours=20, advanced=True,
      problem="Mountain relays see variable radio links; weather records must survive multi-day outages.",
      outcome="A LoRa relay logs climate records with GPS time to SD and forwards them to a valley gateway when the link is available.",
      objectives="Timestamp records from GPS time|Maintain a durable forward queue|Detect link quality from acknowledgements",
      use_cases="Mountain weather study|Remote ski area|Watershed monitoring",
      algorithm="Each record carries a sequence number; an ACK from the gateway advances the pointer; missing ACKs keep records for retry.",
      logic="""static uint32_t seq = 0; seq++;
char buf[200];
snprintf(buf, sizeof(buf), "%lu,%.6f,%.6f,%.1f,%.1f,%.1f,%s", (unsigned long)seq, lat, lng, temperature, humidity, pressure, "PENDING_ACK");
payload = String(buf); logLine = payload;""",
      tests="Block the gateway and confirm PENDING_ACK rows accumulate|Restore the link and confirm forwarding|Verify GPS time is used when available",
      fails="GPS time unavailable indoors | Fall back to RTC and flag the time source.|LoRa antenna iced over | Use a radome and a weatherproof enclosure.|SD wear | Rotate files and use a high-endurance card."),

    S("beehive-health-monitor", "Beehive Weight and Climate Monitor", "Custom & Interdisciplinary", "Advanced",
      "esp32", ["hx711", "dht22", "lora"], "lora", hours=19, advanced=True,
      problem="Beekeepers need early warning of swarming or starvation; weight and hive climate together are more informative than either alone.",
      outcome="A LoRa node reports hive weight, internal temperature/humidity and a sudden weight-drop alert.",
      objectives="Calibrate a load cell under a full hive|Detect a sudden weight change|Protect electronics from propolis and moisture",
      use_cases="Apiary research|Beekeeping co-op|Interdisciplinary sensing",
      algorithm="A 24 h rolling mean of weight plus a > 1 kg drop within 15 minutes flags a possible swarm; climate is reported with the same frame.",
      logic="""static float wBase = weight_g;
wBase = wBase * 0.999F + weight_g * 0.001F;
float dropKg = (wBase - weight_g) / 1000.0F;
char buf[180];
snprintf(buf, sizeof(buf), "H,%.2f,%.2f,%.1f,%.1f,%s", weight_g/1000.0F, dropKg, temperature, humidity, dropKg > 1.0F ? "SWARM_CHECK":"OK");
payload = String(buf);""",
      tests="Tare and calibrate with a 5 kg known mass|Remove 1 kg quickly and confirm SWARM_CHECK|Verify humidity readings inside the hive",
      fails="Load cell creeps with temperature | Use temperature compensation and a stable mechanical mount.|Propolis jams the scale | Use a standoff and a protective mesh.|DHT22 fails at high humidity | Use an SHT31 with a protective filter cap."),

    S("reactive-light-installation", "Sound-Reactive Light Installation", "Custom & Interdisciplinary", "Intermediate",
      "esp32", ["sound", "ws2812b"], "ble", hours=10,
      problem="Interactive art needs responsive lighting with BLE-configurable palettes and no cloud dependency.",
      outcome="A sound sensor drives an 8-LED visualiser with three palettes selectable over BLE and a local peak-hold effect.",
      objectives="Map sound energy to LED brightness|Implement a peak-hold decay|Allow BLE palette selection",
      use_cases="Art installation|Stage prop|Interactive design course",
      algorithm="A normalised sound index sets brightness; a peak-hold decays 5 % per frame; palettes change hue mapping without reflashing.",
      logic="""static float peak = 0;
float level = constrain(sound_index / 100.0F, 0.0F, 1.0F);
peak = fmaxf(level, peak * 0.95F);
uint8_t hue = (uint8_t)(peak * 255.0F);
for (int i = 0; i < 8; i++) strip.setPixelColor(i, strip.ColorHSV((uint16_t)(hue * 256 + i * 1000), 255, (uint8_t)(peak*180)));
strip.show();
char buf[140];
snprintf(buf, sizeof(buf), "{\\"sound_idx\\":%.1f,\\"peak\\":%.2f,\\"palette\\":1}", sound_index, peak);
payload = String(buf);""",
      tests="Play music and confirm the strip responds|Silence and confirm peak decay|Switch palette over BLE and confirm a hue change",
      fails="Strip flickers | Add a level shifter and a 1000 µF capacitor.|BLE disconnect stalls visuals | Keep the render loop independent of BLE callbacks.|Sound module clips | Lower the module gain or add a divider."),

    S("museum-microclimate-guardian", "Museum Microclimate Guardian", "Custom & Interdisciplinary", "Advanced",
      "esp32", ["sht31", "bh1750", "sdcard"], "wifi_mqtt", hours=16, advanced=True,
      problem="Artifacts are damaged by humidity swings and excess light exposure; a monitor must log exposure dose, not just instantaneous values.",
      outcome="A node logs temperature/humidity/lux and computes cumulative lux-hours with a conservation-oriented alert.",
      objectives="Compute cumulative light exposure (lux·h)|Log microclimate at 5-minute intervals|Flag rapid humidity change",
      use_cases="Museum display case|Archive room|Conservation science course",
      algorithm="Lux-hours are integrated from lux samples; a > 5 %RH change in 15 minutes flags a rapid-change risk for sensitive materials.",
      logic="""static double luxHours = 0.0; static float rh15 = humidity; static uint32_t t15 = 0;
luxHours += lux * (SAMPLE_INTERVAL_MS / 3600000.0);
if (!t15) { t15 = millis(); rh15 = humidity; }
if (millis()-t15 > 900000UL) {
  bool rapid = fabsf(humidity - rh15) > 5.0F;
  char buf[240];
  snprintf(buf, sizeof(buf), "{\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"lux\\":%.1f,\\"lux_hours\\":%.2f,\\"rh_rapid\\":%s}", temperature, humidity, lux, luxHours, rapid?"true":"false");
  payload = String(buf); logLine = payload;
  t15 = millis(); rh15 = humidity;
} else payload = "";""",
      tests="Shine a light and confirm lux-hours accumulate|Rapidly change humidity and confirm the flag|Verify 5-minute CSV rows on SD",
      fails="SHT31 self-heating | Use 1 Hz sampling and a vented enclosure.|BH1750 saturates in sunlight | Use the high-resolution mode 2 or a neutral-density filter.|Data gaps | Buffer to SD during network outages."),

    S("weather-balloon-tracker", "DIY Weather Balloon Tracker Prototype", "Custom & Interdisciplinary", "Advanced",
      "esp32", ["gps", "bme280", "rtc", "sdcard", "gsm"], "gsm", hours=24, advanced=True,
      problem="High-altitude prototypes need GPS, climate and a recovery plan, with explicit regulatory and safety limits.",
      outcome="A tracker logs position, pressure, temperature and altitude estimate locally while sending sparse cellular fixes during ascent.",
      objectives="Estimate altitude from barometric pressure|Log at high rate to SD|Document aviation and tethered-balloon regulations",
      use_cases="Tethered balloon experiment|Atmospheric science class|High-altitude prototyping",
      algorithm="Altitude is estimated from the barometric formula; SD logs at 1 Hz; cellular fixes are sent only below a configurable altitude ceiling.",
      logic="""float altitude_m = 44330.0F * (1.0F - powf(pressure / 1013.25F, 0.1903F));
static uint32_t seq = 0; seq++;
char buf[240];
snprintf(buf, sizeof(buf), "%lu,%s,%.6f,%.6f,%.0f,%.1f,%.1f", (unsigned long)seq, timestamp, lat, lng, altitude_m, temperature, pressure);
payload = String(buf); logLine = payload;""",
      tests="Compare altitude estimate against a known elevation|Verify 1 Hz logging to SD|Confirm cellular use is disabled above the configured ceiling",
      fails="GPS loses lock at altitude | Use a GPS rated for high-altitude/high-dynamics mode.|Cold soaks battery | Insulate the enclosure and use a cold-rated cell.|Regulatory breach | Only fly tethered, below the documented ceiling, with local permission."),

    S("compost-process-monitor", "Community Compost Process Monitor", "Custom & Interdisciplinary", "Intermediate",
      "esp32", ["soil_cap", "gas_mq135", "lora"], "lora", hours=12,
      problem="Community compost piles fail silently when moisture or aeration drifts; a low-power node can guide volunteers.",
      outcome="A LoRa node reports pile moisture and a relative gas index with a simple aeration recommendation.",
      objectives="Adapt a soil probe for compost moisture|Baseline a gas sensor outdoors|Give an actionable, transparent recommendation",
      use_cases="Community garden|Municipal compost pilot|Interdisciplinary STEM project",
      algorithm="Moisture below 40 % or a relative gas index above its baseline by 20 points recommends turning or watering, with the rule published in the frame.",
      logic="""static float base = gas_index;
base = base * 0.995F + gas_index * 0.005F;
float delta = gas_index - base;
const char* action = (soil_pct < 40.0F) ? "WATER" : (delta > 20.0F) ? "TURN" : "OK";
char buf[150];
snprintf(buf, sizeof(buf), "C,%.1f,%.1f,%.1f,%s", soil_pct, gas_index, delta, action);
payload = String(buf);""",
      tests="Dry the probe and confirm WATER|Expose the MQ-135 to a mild vapour and confirm TURN|Verify a 15-minute LoRa heartbeat",
      fails="Gas sensor humidity sensitivity | Log the moisture with the index and treat gas as relative only.|Probe corrodes | Use a capacitive probe and remove power between samples.|False recommendations | Validate the thresholds with a compost thermometer."),
]
