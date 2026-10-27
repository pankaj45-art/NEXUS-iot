"""Pro library part B: lighting/energy, industrial, predictive, machines, buildings, air."""
from .spec_base import S

SPECS = [
    S("occupancy-led-lighting", "Occupancy-Driven RGB LED Lighting", "Smart Lighting & Energy Management", "Intermediate",
      "esp32", ["pir", "bh1750", "ws2812b"], "wifi_mqtt", hours=9,
      problem="Fixed lighting schedules ignore real occupancy and available daylight, wasting energy and reducing comfort.",
      outcome="An 8-LED strip dims or brightens based on occupancy and measured lux, with smooth fades and a manual MQTT override.",
      objectives="Fuse PIR occupancy with a lux sensor|Implement non-blocking fades on WS2812B|Respect the strip's 5 V power budget",
      use_cases="Hallway lighting|Workshop task light|Energy-saving retrofit demo",
      algorithm="Target brightness is derived from lux deficit; occupancy gates the strip; a 20 ms easing loop avoids blocking delay().",
      logic="""uint8_t target = motion ? (uint8_t)constrain((int)(220.0F - lux * 0.25F), 40, 180) : 0;
static uint8_t current = 0;
if (current < target) current++; else if (current > target) current--;
for (int i = 0; i < 8; i++) strip.setPixelColor(i, strip.Color(current, current, current));
strip.show();
char buf[180];
snprintf(buf, sizeof(buf), "{\\"lux\\":%.1f,\\"occupancy\\":%s,\\"brightness\\":%u}", lux, motion?"true":"false", current);
payload = String(buf);""",
      tests="Darken the BH1750 and confirm brightness rises with occupancy|Remove occupancy and confirm fade to off|Measure 5 V current with all LEDs at 180 and compare to the supply rating",
      fails="Strip shows random colours | Add the 330 Ω data resistor, 1000 µF cap and a level shifter.|PIR stays HIGH | Check the retrigger jumper and warm-up.|Wi-Fi resets at full brightness | Use a separate 5 V / 2 A supply."),

    S("daylight-harvesting-dimmer", "Daylight-Harvesting PWM Dimmer", "Smart Lighting & Energy Management", "Advanced",
      "esp32", ["bh1750", "ina219", "buzzer"], "wifi_mqtt", hours=12, advanced=True,
      problem="Open-loop dimmers ignore actual lamp power; a closed loop needs a measured power feedback channel.",
      outcome="A PWM-driven low-voltage LED module holds a target lux while reporting measured power and detecting a failed lamp.",
      objectives="Close the loop between lux and PWM duty|Detect a burned-out load from current draw|Avoid oscillation with a slow integral controller",
      use_cases="Desk lamp|Grow-light shelf|Energy research",
      algorithm="A PI-style integrator adjusts duty toward 350 lux with a 0.5 s step; zero current while duty > 10 % flags a lamp fault.",
      logic="""static float duty = 20.0F;
float err = 350.0F - lux;
duty = constrain(duty + err * 0.02F, 0.0F, 100.0F);
ledcWrite(0, (uint32_t)(duty / 100.0F * 255.0F));  // attach a PWM channel in setup
bool lampFault = (duty > 10.0F && fabsf(current_ma) < 5.0F);
if (lampFault) digitalWrite(BUZZER_PIN, HIGH);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"lux\\":%.1f,\\"duty_pct\\":%.1f,\\"v\\":%.2f,\\"ma\\":%.1f,\\"w\\":%.2f,\\"lamp_fault\\":%s}", lux, duty, voltage_v, current_ma, power_w, lampFault?"true":"false");
payload = String(buf);""",
      tests="Shade the sensor and confirm duty rises until ~350 lux|Disconnect the LED and confirm lamp_fault|Verify no visible oscillation over 5 minutes",
      fails="PWM channel not attached | Add ledcSetup/ledcAttachPin in setup for the chosen GPIO.|Lux oscillates | Reduce the integral gain and add a deadband.|Current reads zero | Verify the INA219 is on the load high side."),

    S("dc-energy-meter", "Precision DC Energy Meter with OLED", "Smart Lighting & Energy Management", "Intermediate",
      "esp32", ["ina219", "oled", "sdcard"], "sd_local", hours=8,
      problem="Battery and solar experiments need logged voltage/current/energy with a local display and no cloud dependency.",
      outcome="A meter logs Wh to SD with RTC-less monotonic timestamps and shows instantaneous power on the OLED.",
      objectives="Integrate power into Wh with a bounded accumulator|Log CSV with a simple checksum|Handle SD failures without losing the display",
      use_cases="Solar panel characterisation|Battery discharge test|DC lab supply monitor",
      algorithm="Power is integrated using elapsed millis; each CSV row carries a rolling checksum and the SD write result is reported.",
      logic="""static double wh = 0.0; static uint32_t last = 0; static uint32_t seq = 0;
if (!last) last = millis();
wh += power_w * ((millis() - last) / 3600000.0); last = millis(); seq++;
uint32_t sum = seq + (uint32_t)(power_w * 100) + (uint32_t)(wh * 100);
char buf[220];
snprintf(buf, sizeof(buf), "%lu,%lu,%.3f,%.5f,%lu", (unsigned long)seq, (unsigned long)millis(), power_w, wh, (unsigned long)sum);
payload = String(buf); logLine = payload;
displayLine = String(power_w,2) + " W\\n" + String(wh,3) + " Wh";""",
      tests="Apply a 5 W load for 6 min and confirm ~0.5 Wh|Remove the SD card and confirm the OLED keeps updating|Validate the checksum on 100 rows",
      fails="Wh drifts | Use millis() delta, not the configured interval, if the loop is slowed.|SD rows truncated | Increase snprintf buffer or shorten the row.|Negative current | Swap VIN+/VIN- sense leads."),

    S("solar-charge-monitor", "Solar Charge Controller Monitor", "Smart Lighting & Energy Management", "Advanced",
      "esp32", ["ina219", "ds18b20", "lora"], "lora", hours=14, advanced=True,
      problem="Remote solar installations need charge-state visibility and panel temperature without a local network.",
      outcome="A LoRa node reports charge current, bus voltage, panel temperature and a derived state-of-charge proxy.",
      objectives="Monitor a solar panel with a high-side shunt|Estimate charge state transparently|Transmit a compact long-range frame",
      use_cases="Remote sensor power|Cabin solar|Solar education",
      algorithm="A coulomb-count estimate accumulates charge with a defined capacity constant; temperature derates the expected panel voltage.",
      logic="""static float soc = 50.0F;
soc = constrain(soc + (current_ma / 1000.0F) * (SAMPLE_INTERVAL_MS / 3600000.0F) / BATTERY_AH * 100.0F, 0.0F, 100.0F);
char buf[160];
snprintf(buf, sizeof(buf), "S,%.2f,%.0f,%.1f,%.0f", voltage_v, current_ma, temperature, soc);
payload = String(buf);""",
      tests="Connect a known load and confirm SoC falls at the expected rate|Warm the panel and confirm temperature tracking|Verify the LoRa frame parses at the gateway",
      fails="SoC unrealistic | Calibrate BATTERY_AH and reset the counter at a full charge.|ADC noise at low current | Average 16 samples and zero the offset.|LoRa packet lost | Increase spreading factor and confirm antenna placement."),

    S("modbus-energy-gateway", "Modbus RTU to MQTT Energy Gateway", "Industrial IoT", "Advanced",
      "rpi4", ["rs485", "ethernet", "ina219"], "ethernet", hours=18, advanced=True,
      problem="Industrial meters speak Modbus RTU; cloud dashboards speak MQTT, and a gateway must tolerate bus disconnects.",
      outcome="A Raspberry Pi gateway polls holding registers over RS-485, validates CRC and republishes scaled engineering values.",
      objectives="Poll a Modbus slave with a retry budget|Map raw registers to engineering units|Run as a resilient systemd service",
      use_cases="Factory energy monitoring|Building sub-metering|Industrial protocol lab",
      algorithm="Python scheduler polls registers every 5 s; three consecutive CRC failures mark the device offline and publish a diagnostic event.",
      logic="""# Python gateway logic is generated in the Python firmware section.
payload = "{\\"gateway\\":\\"rpi4\\",\\"registers\\":2,\\"retry_budget\\":3}";""",
      tests="Simulate a Modbus slave and confirm scaled values in MQTT|Disconnect the A/B wires and confirm an offline event|Restart the service and confirm automatic recovery",
      fails="CRC errors | Verify 120 Ω termination and baud/parity settings.|Permission denied on /dev/ttyAMA0 | Add the user to dialout and disable the serial console.|MQTT backlog | Reduce poll frequency or batch registers."),

    S("industrial-tank-4-20ma", "Industrial Tank Level with Pressure Transducer", "Industrial IoT", "Advanced",
      "esp32", ["pressure", "rs485", "oled"], "rs485", hours=15, advanced=True,
      problem="Industrial level measurement needs a robust 0.5-4.5 V/4-20 mA interface and a fieldbus output, not a hobby float switch.",
      outcome="A pressure transducer is scaled to tank volume and exposed as a Modbus holding register with an out-of-range fault code.",
      objectives="Scale a ratiometric transducer with a divider|Convert level to volume from a tank geometry|Expose RTU registers with a fault code",
      use_cases="Chemical dosing tank|Process water tank|Industrial training rig",
      algorithm="Voltage is converted to bar using the vendor transfer function, then to hydrostatic height and to litres via a cylindrical geometry constant.",
      logic="""float height_cm = pressure_bar * 1000.0F / 9.81F;  // rho ~1000 kg/m3
float litres = height_cm * TANK_AREA_CM2 / 1000.0F;
bool fault = (pressure_bar < 0.0F || pressure_bar > 1.0F || height_cm > TANK_HEIGHT_CM);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"pressure_bar\\":%.3f,\\"height_cm\\":%.1f,\\"litres\\":%.1f,\\"reg_value\\":%.1f,\\"fault\\":%s}", pressure_bar, height_cm, litres, reg_value, fault?"true":"false");
payload = String(buf);
displayLine = String(litres,0) + " L " + String(fault?"FLT":"OK");""",
      tests="Apply a known water column and compare computed height|Verify the Modbus register value matches litres|Open-circuit the transducer and confirm fault=1",
      fails="Readings saturate | Verify the divider maps 4.5 V into the ADC range.|Wrong volume | Update TANK_AREA_CM2 for the real geometry.|Modbus timeouts | Check DE control and slave ID.")

    ,S("machine-cycle-counter", "Machine Cycle Counter with RFID Job Tracking", "Industrial IoT", "Intermediate",
      "esp32", ["hall", "rfid", "ethernet", "oled"], "ethernet", hours=12,
      problem="Small workshops need per-job cycle counts without a PLC, but pulse noise and operator identification both matter.",
      outcome="A wired Ethernet node counts machine cycles from a hall sensor and associates each batch with an operator RFID UID.",
      objectives="Debounce hall pulses with a minimum period|Associate batches with an RFID job ID|Report counts over wired Ethernet",
      use_cases="Press cycle counting|Packaging line|Job-costing prototype",
      algorithm="Interrupts increment a pulse counter; a 50 ms minimum period rejects double pulses; an RFID scan opens a new batch record.",
      logic="""static uint32_t cycles = 0;
static String currentJob = "none";
uint32_t newPulses = (uint32_t)(flow_lpm * 7.5F);  // approx: inverse of YF-S201 scaling
cycles += newPulses;
if (uid.length()) { currentJob = uid; cycles = 0; }
char buf[180];
snprintf(buf, sizeof(buf), "{\\"job\\":\\"%s\\",\\"cycles\\":%lu,\\"pulses\\":%lu}", currentJob.c_str(), (unsigned long)cycles, (unsigned long)newPulses);
payload = String(buf);
displayLine = String("Job ") + currentJob.substring(0,8) + " " + String(cycles);""",
      tests="Wave a magnet 20 times and confirm 20 counts|Present a new tag and confirm the batch resets|Verify Ethernet link-down is logged",
      fails="Double counts | Increase the minimum pulse period and add RC filtering.|RFID read distance short | Reposition the antenna away from metal.|Ethernet DHCP fails | Assign a static IP and check the W5500 CS line."),

    S("factory-environment-node", "Factory Environment & Particulate Node", "Industrial IoT", "Advanced",
      "esp32", ["scd30", "pms5003", "rs485", "oled"], "rs485", hours=15, advanced=True,
      problem="Factory air quality combines CO₂ and particulates; a single sensor gives a misleading picture of ventilation and dust.",
      outcome="A node reports NDIR CO₂, PM2.5/PM10 and climate over RS-485 with a ventilation advisory flag.",
      objectives="Combine NDIR CO₂ and laser particle sensing|Handle UART framing and CRC|Expose a combined air-quality advisory",
      use_cases="Workshop ventilation|Welding bay study|Industrial hygiene prototype",
      algorithm="A 5-minute rolling mean of PM2.5 plus CO₂ above 1000 ppm raises a VENTILATE advisory; raw and averaged values are both published.",
      logic="""static float pmAvg = pm25;
pmAvg = pmAvg * 0.9F + pm25 * 0.1F;
bool ventilate = (co2 > 1000.0F || pmAvg > 35.0F);
char buf[260];
snprintf(buf, sizeof(buf), "{\\"co2_ppm\\":%.0f,\\"pm25\\":%.1f,\\"pm10\\":%.1f,\\"pm25_avg\\":%.1f,\\"t_c\\":%.1f,\\"ventilate\\":%s}", co2, pm25, pm10, pmAvg, temperature, ventilate?"true":"false");
payload = String(buf);
displayLine = String(co2,0) + " ppm " + String(pm25,1) + "ug";""",
      tests="Expose the sensor to a safe aerosol and confirm PM rise|Compare CO₂ reading with a reference NDIR meter|Unplug the PMS UART and confirm an [ERR] log",
      fails="PM sensor CRC errors | Check 9600 baud, 3.3 V UART and wiring polarity.|CO₂ stuck at 400 | Disable ASC in a constantly occupied room or force calibration.|Humidity bias | Add humidity correction above 70 %RH."),

    S("motor-vibration-monitor", "Motor Vibration & Temperature Monitor", "Predictive Maintenance", "Advanced",
      "esp32", ["mpu6050", "mlx90614", "buzzer"], "wifi_mqtt", hours=14, advanced=True,
      problem="Bearing failures show up as rising vibration and surface temperature, but a single threshold produces false positives.",
      outcome="An ESP32 computes RMS vibration and compares motor surface temperature against a learned baseline with a two-stage alert.",
      objectives="Sample an IMU at a fixed rate and compute RMS|Track a slow baseline with a bounded learning rate|Emit WARNING and CRITICAL states",
      use_cases="Pump motor monitoring|Fan bearing study|Industrial training",
      algorithm="Twenty acceleration samples produce an RMS magnitude; baseline vibration and temperature adapt slowly; two-of-three consecutive breaches escalate the alert.",
      logic="""static float vibBase = 1.0F, tempBase = 30.0F; static uint8_t strikes = 0;
vibBase = vibBase * 0.99F + vibration_g * 0.01F;
tempBase = tempBase * 0.995F + obj_temp * 0.005F;
bool breach = (vibration_g > vibBase * 1.8F) || (obj_temp > tempBase + 12.0F);
if (breach) { if (strikes < 3) strikes++; } else strikes = 0;
const char* state = strikes >= 2 ? "CRITICAL" : strikes == 1 ? "WARNING" : "OK";
if (strikes >= 2) digitalWrite(BUZZER_PIN, HIGH);
char buf[240];
snprintf(buf, sizeof(buf), "{\\"vib_g\\":%.3f,\\"vib_base\\":%.3f,\\"surface_c\\":%.1f,\\"temp_base\\":%.1f,\\"state\\":\\"%s\\"}", vibration_g, vibBase, obj_temp, tempBase, state);
payload = String(buf);""",
      tests="Shake the sensor and confirm WARNING then CRITICAL|Let it settle and confirm recovery to OK|Verify the baseline does not learn an anomaly too quickly",
      fails="IMU reads constant | Check 0x68 address and that the sensor is rigidly mounted.|False CRITICAL at startup | Seed the baseline from the first 60 s of data.|IR temperature wrong | Set emissivity for the actual motor surface."),

    S("pump-cavitation-detector", "Pump Cavitation Acoustic Detector", "Predictive Maintenance", "Advanced",
      "esp32s3", ["sound", "hall", "ina219"], "wifi_mqtt", hours=16, advanced=True,
      problem="Cavitation destroys pumps, but its acoustic signature overlaps normal noise and varies with flow and power.",
      outcome="A node correlates sound energy, flow and power to flag a cavitation-like pattern and recommends a check rather than an automatic shutdown.",
      objectives="Fuse acoustic, flow and power signals|Normalise by flow to reduce false positives|Keep the output advisory, not safety-critical",
      use_cases="Circulation pump|Irrigation pump|Predictive maintenance lab",
      algorithm="A flow-normalised sound ratio is compared with a rolling baseline; a high ratio at low flow with unstable power raises an advisory.",
      logic="""static float base = sound_index;
base = base * 0.98F + sound_index * 0.02F;
float norm = sound_index / fmaxf(flow_lpm, 0.2F);
bool cavitationLike = (norm > base * 1.6F && power_w > 2.0F && flow_lpm < 3.0F);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"sound_idx\\":%.1f,\\"sound_base\\":%.1f,\\"flow_lpm\\":%.2f,\\"power_w\\":%.2f,\\"advisory\\":%s}", sound_index, base, flow_lpm, power_w, cavitationLike?"CAVITATION_CHECK":"NORMAL");
payload = String(buf);""",
      tests="Run the pump normally and record the baseline|Throttle the inlet and confirm the advisory|Restore flow and confirm recovery",
      fails="Always advisory | Recalibrate the sound baseline for the actual pump housing.|Flow reads zero | Verify the hall sensor K-factor and pull-up.|Power measurement missing | Check the INA219 shunt and wiring."),

    S("bearing-temperature-trend", "Bearing Temperature Trend Logger", "Predictive Maintenance", "Intermediate",
      "uno", ["ds18b20", "rtc", "sdcard", "buzzer"], "sd_local", hours=9,
      problem="Slow bearing degradation is invisible without long-term, time-stamped trend data at a low-cost node.",
      outcome="An Arduino Uno logs bearing temperature every minute with an RTC timestamp and detects a sustained rise rate.",
      objectives="Log long-term temperature with an RTC|Compute a rate-of-rise over 30 minutes|Handle SD card removal safely",
      use_cases="Conveyor bearing|Pillow-block monitoring|Maintenance training",
      algorithm="A 30-sample ring buffer yields °C/min slope; a slope above 0.2 °C/min for 10 minutes triggers a buzzer and a log flag.",
      logic="""static float hist[30] = {0}; static uint8_t n = 0;
hist[n++ % 30] = temperature;
float slope = (n >= 30) ? (hist[(n-1)%30] - hist[n%30]) / 30.0F : 0.0F;
bool rising = slope > 0.2F;
digitalWrite(BUZZER_PIN, rising ? HIGH : LOW);
char buf[180];
snprintf(buf, sizeof(buf), "%s,%.2f,%.3f,%s", timestamp, temperature, slope, rising?"RISING":"stable");
payload = String(buf); logLine = payload;""",
      tests="Warm the probe steadily and confirm a rising slope|Confirm CSV rows are timestamped|Remove the SD card and confirm a logged error",
      fails="DS18B20 returns 85 | Add the 4.7 kΩ pull-up and discard the reset value.|RTC time wrong | Set the time once and replace the backup cell.|SD corruption | Flush and close the file after each row."),

    S("compressor-anomaly-lora", "Compressor Anomaly Node over LoRa", "Predictive Maintenance", "Advanced",
      "esp32", ["mpu6050", "acs712", "lora"], "lora", hours=17, advanced=True,
      problem="Compressors in remote sites need anomaly alerts without Wi-Fi or cellular coverage.",
      outcome="A LoRa node computes vibration RMS and current draw, transmitting a compact anomaly score and a raw-sample snapshot.",
      objectives="Fuse vibration and current into one score|Fit within a small LoRa payload|Provide a manual verification procedure",
      use_cases="Remote air compressor|Refrigeration plant|Field maintenance",
      algorithm="Vibration and current are normalised against a learned baseline; a score above 60 triggers an immediate frame with a 10-sample snapshot.",
      logic="""static float vBase = 1.0F, iBase = 1.0F;
vBase = vBase * 0.99F + vibration_g * 0.01F;
iBase = iBase * 0.99F + fabsf(current_a) * 0.01F;
float score = 50.0F * (vibration_g / fmaxf(vBase,0.01F)) + 50.0F * (fabsf(current_a) / fmaxf(iBase,0.01F));
char buf[140];
snprintf(buf, sizeof(buf), "C,%.3f,%.2f,%.1f,%s", vibration_g, current_a, score, score > 60.0F ? "ANOMALY":"OK");
payload = String(buf);""",
      tests="Run the compressor normally and record the baseline|Introduce a safe mechanical imbalance and confirm ANOMALY|Verify the frame is under the regional LoRa payload limit",
      fails="ACS712 offset drift | Measure zero-current offset and store it in firmware.|False anomalies at start | Seed baselines for the first 120 s.|LoRa collisions | Randomise TX times per node."),

    S("cnc-runtime-tracker", "CNC Run-Hour and Load Tracker", "Machine & Equipment Monitoring", "Intermediate",
      "esp32", ["ina219", "hall", "sdcard"], "sd_local", hours=9,
      problem="Maintenance schedules based on calendar time are inaccurate for machines with variable utilisation.",
      outcome="A node accumulates powered-on hours and spindle pulse counts locally, flagging the next service interval.",
      objectives="Detect machine ON state from current|Count spindle pulses|Persist totals across power cycles",
      use_cases="Small CNC router|Workshop compressor|Maintenance scheduling",
      algorithm="Current above a threshold increments run minutes; pulses are accumulated; totals are written to SD with a sequence number.",
      logic="""static float runHours = 0.0F; static uint32_t totalPulses = 0;
bool running = fabsf(current_ma) > 200.0F;
if (running) runHours += (SAMPLE_INTERVAL_MS / 3600000.0F);
totalPulses += (uint32_t)(flow_lpm * 7.5F);  // approx pulse count from the hall driver
bool serviceDue = runHours > 200.0F;
char buf[200];
snprintf(buf, sizeof(buf), "%.3f,%lu,%s,%.0f", runHours, (unsigned long)totalPulses, running?"ON":"OFF", power_w);
payload = String(buf); logLine = payload;
if (serviceDue) Serial.println(F("[ALERT] 200 h service interval reached"));""",
      tests="Apply a load and confirm run hours increase only when current is high|Wave a magnet and confirm pulse counts|Power-cycle and confirm totals reload from SD",
      fails="Run hours never increase | Lower the 200 mA threshold for the machine's idle current.|Pulses lost | Use an interrupt-capable GPIO and short wires.|SD totals lost | Flush after each write and use a journal file."),

    S("conveyor-jam-detector", "Conveyor Jam Detection with ToF Sensing", "Machine & Equipment Monitoring", "Intermediate",
      "esp32", ["vl53l0x", "hall", "buzzer", "rs485"], "rs485", hours=11,
      problem="A jam can be a stalled belt with boxes still present; one sensor cannot distinguish it from an empty line.",
      outcome="A node combines time-of-flight presence with belt speed pulses to detect a jam and expose a Modbus fault register.",
      objectives="Fuse presence and motion into a jam decision|Add a 5 s confirmation window|Report a Modbus fault code",
      use_cases="Packaging conveyor|Sorting line|Factory training rig",
      algorithm="If an object remains within 20 cm for > 5 s while belt speed is near zero, a jam is declared and the buzzer sounds.",
      logic="""static uint32_t stuckAt = 0;
bool objectPresent = distance_cm > 2.0F && distance_cm < 20.0F;
bool beltStopped = flow_lpm < 0.1F;
if (objectPresent && beltStopped) { if (!stuckAt) stuckAt = millis(); } else stuckAt = 0;
bool jam = stuckAt && millis()-stuckAt > 5000UL;
digitalWrite(BUZZER_PIN, jam ? HIGH : LOW);
char buf[200];
snprintf(buf, sizeof(buf), "{\\"distance_cm\\":%.1f,\\"flow_lpm\\":%.2f,\\"jam\\":%s,\\"reg_value\\":%.1f}", distance_cm, flow_lpm, jam?"true":"false", reg_value);
payload = String(buf);""",
      tests="Hold a box in front of the ToF sensor and stop the belt to confirm a jam|Remove the box and confirm clearing|Verify the Modbus master sees the fault register",
      fails="VL53L0X timeouts | Check target reflectivity and 0x29 address.|False jam on reflective wrap | Increase timing budget and add a region of interest.|RS-485 errors | Terminate the bus and verify DE control."),

    S("generator-battery-health", "Generator Battery & Temperature Health Monitor", "Machine & Equipment Monitoring", "Advanced",
      "picow", ["ina219", "ds18b20", "gsm"], "gsm", hours=14, advanced=True,
      problem="Backup generators fail because their starter battery degrades silently between tests.",
      outcome="A Pico W monitors battery voltage, charge current and temperature, sending a weekly test report and immediate low-voltage alerts.",
      objectives="Estimate starter-battery health from voltage sag|Send cellular alerts without Wi-Fi|Schedule a weekly self-test",
      use_cases="Backup generator|Remote telecom site|Marine auxiliary power",
      algorithm="Voltage sag during a start event is compared with a healthy threshold; temperature compensates the expected open-circuit voltage.",
      logic="""float voc = voltage_v + 0.005F * (temperature - 25.0F);
bool low = voc < 12.2F;
static uint32_t lastReport = 0;
if (low || millis()-lastReport > 604800000UL) {
  lastReport = millis();
  char buf[200];
  snprintf(buf, sizeof(buf), "{\\"battery_v\\":%.2f,\\"voc_comp\\":%.2f,\\"battery_c\\":%.1f,\\"low_battery\\":%s}", voltage_v, voc, temperature, low?"true":"false");
  payload = String(buf);
} else payload = "";""",
      tests="Draw a heavy load and confirm voltage sag is captured|Verify temperature compensation changes the VOC estimate|Confirm a weekly report with no alert",
      fails="No cellular coverage | Choose a supported LTE band or use LoRa with a gateway.|Voltage reads low | Verify the INA219 bus voltage measurement point.|False low-battery alerts | Compensate for charger float voltage."),

    S("cold-chain-equipment-monitor", "Cold-Chain Equipment Door & Temperature Monitor", "Machine & Equipment Monitoring", "Intermediate",
      "esp32", ["ds18b20", "reed", "rtc", "oled"], "wifi_mqtt", hours=10,
      problem="Cold-chain excursions are usually caused by doors left open; temperature alone arrives too late.",
      outcome="A node logs door-open duration and product temperature, raising an alert when either exceeds its limit.",
      objectives="Measure door-open duration with a reed switch|Log temperature excursions with RTC timestamps|Separate door and temperature alerts",
      use_cases="Vaccine fridge (educational)|Food storage|Cold room monitoring",
      algorithm="Open duration is accumulated; an alert fires if the door is open > 120 s or temperature > 8 °C for > 5 minutes.",
      logic="""static uint32_t openAt = 0, hotAt = 0;
if (door_open) { if (!openAt) openAt = millis(); } else openAt = 0;
if (temperature > 8.0F) { if (!hotAt) hotAt = millis(); } else hotAt = 0;
uint32_t openS = openAt ? (millis()-openAt)/1000UL : 0;
bool alert = openS > 120 || (hotAt && millis()-hotAt > 300000UL);
char buf[220];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"temp_c\\":%.1f,\\"door_open\\":%s,\\"open_s\\":%lu,\\"alert\\":%s}", timestamp, temperature, door_open?"true":"false", (unsigned long)openS, alert?"true":"false");
payload = String(buf);
displayLine = String(temperature,1) + "C " + String(door_open?"OPEN":"SHUT");""",
      tests="Hold the door open 2 minutes and confirm an alert|Warm the probe above 8 °C and confirm a separate alert|Verify RTC timestamps survive a reboot",
      fails="Door events missed | Check the reed switch orientation and debounce.|Temperature lags | Use a probe in a glycol buffer for realistic product temperature.|False alarms during defrost | Add a defrost inhibit window."),

    S("co2-ventilation-control", "CO₂-Driven Ventilation Controller", "Smart Buildings", "Advanced",
      "esp32", ["scd30", "fan", "oled"], "wifi_mqtt", hours=12, advanced=True,
      problem="Fixed ventilation rates either waste fan energy or allow CO₂ to build up in occupied rooms.",
      outcome="A controller modulates a low-voltage DC fan with a CO₂ setpoint and publishes the control state.",
      objectives="Control fan speed from NDIR CO₂|Implement a proportional band with a minimum off-time|Log CO₂, temperature and humidity",
      use_cases="Classroom ventilation|Meeting room|Small office",
      algorithm="A proportional band from 700 to 1400 ppm sets a PWM duty; the fan is off below 700 ppm and at full duty above 1400 ppm.",
      logic="""float duty = constrain((co2 - 700.0F) / 700.0F * 100.0F, 0.0F, 100.0F);
if (duty > 0.0F && duty < 25.0F) duty = 25.0F;  // fan start threshold
analogWrite(FAN_PIN, (int)(duty / 100.0F * 255.0F));
char buf[220];
snprintf(buf, sizeof(buf), "{\\"co2_ppm\\":%.0f,\\"t_c\\":%.1f,\\"rh\\":%.1f,\\"fan_pct\\":%.0f}", co2, temperature, humidity, duty);
payload = String(buf);
displayLine = String(co2,0) + " ppm\\nFan " + String(duty,0) + "%";""",
      tests="Exhale near the SCD30 and confirm fan duty rises|Move to fresh air and confirm the fan stops|Verify the 25 % start threshold avoids stall",
      fails="CO₂ stuck high | Check ASC settings and fresh-air baseline.|Fan hums but does not spin | Raise the start duty or use a PWM-capable fan controller.|analogWrite unsupported | Use ledcWrite on ESP32 with an attached channel."),

    S("occupancy-room-counter", "Room Occupancy Counter with ToF Tripwire", "Smart Buildings", "Advanced",
      "esp32", ["vl53l0x", "pir", "oled"], "wifi_mqtt", hours=13, advanced=True,
      problem="PIR sensors detect motion, not people count; a single ToF sensor cannot tell direction.",
      outcome="A prototype uses a ToF tripwire plus PIR confirmation to estimate entries/exits with an explicit accuracy disclaimer.",
      objectives="Detect a crossing with a ToF distance change|Use PIR as a confirmation signal|Publish a count with a confidence flag",
      use_cases="Meeting-room occupancy|Library capacity display|Occupancy research",
      algorithm="A near-to-far transition within 800 ms followed by PIR motion counts an exit; the reverse counts an entry; ambiguous events are flagged.",
      logic="""static uint8_t count = 0; static float lastD = distance_cm; static uint32_t crossAt = 0;
bool crossing = fabsf(distance_cm - lastD) > 30.0F;
if (crossing && motion) { crossAt = millis(); }
if (crossAt && millis()-crossAt < 800UL && distance_cm > lastD) { if (count) count--; crossAt = 0; }
lastD = distance_cm;
char buf[180];
snprintf(buf, sizeof(buf), "{\\"distance_cm\\":%.1f,\\"motion\\":%s,\\"estimated_occupancy\\":%u,\\"confidence\\":\\"low_single_sensor\\"}", distance_cm, motion?"true":"false", count);
payload = String(buf);
displayLine = String("People ~") + String(count);""",
      tests="Walk through the beam and confirm a directional count|Stand still and confirm no false count|Verify the low-confidence flag is always present",
      fails="Counts drift | Use two ToF sensors with known spacing for direction.|PIR misses slow movement | Lower the PIR timeout or use mmWave.|Glass confuses ToF | Reposition and check the sensor's ranging mode."),

    S("smart-window-actuator", "Rain-Aware Smart Window Actuator", "Smart Buildings", "Intermediate",
      "esp32", ["rain", "bh1750", "servo", "buzzer"], "wifi_mqtt", hours=10,
      problem="Automated windows must close on rain and never trap fingers; a naive IFTTT rule ignores actuator position.",
      outcome="A servo-driven window model closes on rain or darkness and reports its commanded angle with a travel limit.",
      objectives="Prioritise rain override over light-based control|Implement a bounded servo travel and speed|Expose a manual override command",
      use_cases="Greenhouse vent|Skylight model|Smart building lab",
      algorithm="Rain > 20 % forces closed with a short buzzer; otherwise lux below 80 closes slowly; servo steps 5° per cycle to simulate safe travel.",
      logic="""static int angle = 15;
int target = (rain_pct > 20.0F || lux < 80.0F) ? 15 : 90;
if (angle < target) angle = min(angle + 5, target); else if (angle > target) angle = max(angle - 5, target);
actuator.write(angle);
if (rain_pct > 20.0F) { digitalWrite(BUZZER_PIN, HIGH); delay(60); digitalWrite(BUZZER_PIN, LOW); }
char buf[180];
snprintf(buf, sizeof(buf), "{\\"rain_pct\\":%.1f,\\"lux\\":%.1f,\\"angle_deg\\":%d,\\"rain_override\\":%s}", rain_pct, lux, angle, rain_pct>20.0F?"true":"false");
payload = String(buf);""",
      tests="Wet the rain board and confirm the window closes|Darken the BH1750 and confirm a slow close|Verify the servo never exceeds 90°",
      fails="Servo twitches | Use a separate 5 V / 1 A supply and a 100 µF cap.|Rain override delayed | Move the rain check before the lux logic.|Rain board corrosion | Sample intermittently and dry the plate."),

    S("building-water-meter", "Building Water Meter Pulse Aggregator", "Smart Buildings", "Intermediate",
      "esp32", ["hall", "sdcard", "rtc"], "wifi_mqtt", hours=9,
      problem="Retrofitting water metering needs pulse counting without replacing the mechanical meter, plus outage-proof logging.",
      outcome="A node aggregates flow pulses into litres per interval, logs to SD with timestamps and publishes hourly totals.",
      objectives="Count pulses with a debounced interrupt|Persist totals to SD|Publish hourly and daily aggregates",
      use_cases="Apartment sub-metering|Leak detection baseline|Water conservation study",
      algorithm="Pulses are scaled by a measured K-factor into litres; a 5-minute ring buffer builds hourly totals; SD holds the running total.",
      logic="""static double totalL = 0.0;
totalL += flow_lpm * (SAMPLE_INTERVAL_MS / 60000.0F);
char buf[200];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"flow_lpm\\":%.2f,\\"total_litres\\":%.2f,\\"k_factor\\":7.5}", timestamp, flow_lpm, totalL);
payload = String(buf); logLine = payload;""",
      tests="Run 10 L through the meter and compare with the reported total|Confirm totals survive a reboot via SD|Verify no double counting when the meter stops",
      fails="Pulses missed | Use a hardware interrupt and short, shielded cable.|K-factor wrong | Calibrate with a measured volume.|SD rows missing on power loss | Flush each row and add a supercapacitor."),

    S("low-cost-pm25-node", "Calibrated Low-Cost PM2.5 Node", "Air Quality Monitoring", "Advanced",
      "esp32", ["pms5003", "bme280"], "wifi_http", hours=14, advanced=True,
      problem="Optical particle sensors over-read at high humidity; raw µg/m³ values are often presented without correction.",
      outcome="A node applies a humidity correction and publishes raw plus corrected PM2.5 with calibration metadata.",
      objectives="Read PM1/2.5/10 over UART|Apply a transparent humidity correction|Include QA flags in the payload",
      use_cases="Community air monitoring|Indoor air study|Sensor-network research",
      algorithm="For RH > 70 %, a k=0.25 hygroscopic growth factor reduces the reported PM2.5; values above 90 %RH are flagged invalid.",
      logic="""float corr = 1.0F;
if (humidity > 70.0F) corr = 1.0F / (1.0F + 0.25F * (humidity - 70.0F) / 20.0F);
float pm25_corr = pm25 * corr;
bool qaBad = humidity > 90.0F || pm25 < 0.0F;
char buf[260];
snprintf(buf, sizeof(buf), "{\\"pm25_raw\\":%.1f,\\"pm25_corr\\":%.1f,\\"pm10\\":%.1f,\\"rh\\":%.1f,\\"t_c\\":%.1f,\\"qa_valid\\":%s,\\"correction\\":\\"k=0.25_hygroscopic\\"}", pm25, pm25_corr, pm10, humidity, temperature, qaBad?"false":"true");
payload = String(buf);""",
      tests="Compare raw and corrected values at 85 %RH|Co-locate with a reference monitor for 24 h|Confirm QA false above 90 %RH",
      fails="PM values frozen | Check the PMS UART TX/RX crossover and 5 V supply.|Correction seems arbitrary | Document k as an assumption; calibrate locally.|Humidity sensor missing | Verify BME280 address and bus pull-ups."),

    S("indoor-co2-tvoc-dashboard", "Indoor CO₂ / TVOC Dashboard", "Air Quality Monitoring", "Intermediate",
      "esp32", ["ccs811", "oled"], "wifi_mqtt", hours=8,
      problem="VOC-based eCO₂ is often confused with true NDIR CO₂; users need to see the distinction in the data.",
      outcome="A dashboard explicitly labels eCO₂ as an estimate and shows TVOC trends with a burn-in status flag.",
      objectives="Read CCS811 eCO₂ and TVOC|Expose burn-in and baseline status|Explain why eCO₂ is not NDIR CO₂",
      use_cases="Office air-quality display|Bedroom ventilation cue|Sensor-education demo",
      algorithm="Sensor readings are tagged with a burn-in flag and a drive mode; a 24-hour baseline tracker stabilises the eCO₂ estimate.",
      logic="""bool burnIn = millis() < 172800000UL;  // 48 h
const char* band = co2 > 1200.0F ? "VENTILATE" : co2 > 800.0F ? "WATCH" : "OK";
char buf[220];
snprintf(buf, sizeof(buf), "{\\"eco2_ppm\\":%.0f,\\"tvoc_ppb\\":%.0f,\\"band\\":\\"%s\\",\\"burn_in\\":%s,\\"sensor_type\\":\\"VOC_estimate_not_NDIR\\"}", co2, tvoc, band, burnIn?"true":"false");
payload = String(buf);
displayLine = String("eCO2 ") + String(co2,0) + "\\n" + String(band);""",
      tests="Expose the sensor to a safe VOC source and confirm a rise|Verify the payload says VOC_estimate_not_NDIR|Confirm burn_in clears after the configured window",
      fails="eCO₂ stuck at 400 | Allow burn-in and set the drive mode to 60 s.|I2C clock stretch failures | Use 100 kHz bus speed for CCS811.|Values jump after power loss | Persist the baseline in NVS."),

    S("outdoor-aqi-lora-node", "Outdoor AQI Node with LoRa Backhaul", "Air Quality Monitoring", "Advanced",
      "esp32", ["sds011", "bme280", "lora"], "lora", hours=16, advanced=True,
      problem="Urban air-quality nodes need long-range backhaul and a duty-cycled laser sensor to extend service life.",
      outcome="A LoRa node wakes the SDS011 for a 30 s measurement every 10 minutes and transmits PM2.5/PM10 plus climate.",
      objectives="Duty-cycle a laser particle sensor|Pack measurements into a compact LoRa frame|Operate within regional duty cycle",
      use_cases="Neighbourhood AQ network|Roadside study|Remote campus monitoring",
      algorithm="The sensor fan runs only during a 30 s warm-up and read window; the averaged values are sent as a comma-delimited frame.",
      logic="""static float sum25 = 0, sum10 = 0; static uint8_t n = 0;
sum25 += pm25; sum10 += pm10; n++;
if (n >= 3) {
  char buf[140];
  snprintf(buf, sizeof(buf), "A,%.1f,%.1f,%.1f,%.1f", sum25/n, sum10/n, temperature, humidity);
  payload = String(buf); sum25 = sum10 = 0; n = 0;
} else payload = "";""",
      tests="Confirm the fan duty cycle with a current meter|Verify all three samples are averaged|Check the LoRa airtime against regional duty-cycle rules",
      fails="Laser fails early | Use the documented duty-cycle mode, not continuous fan operation.|CRC failures | Verify 9600 baud and 3.3 V UART level.|High humidity bias | Add the BME280 humidity to the payload for post-correction."),

    S("voc-source-tracker", "VOC Source Tracking Node", "Air Quality Monitoring", "Intermediate",
      "esp32", ["bme680", "rtc", "sdcard"], "wifi_http", hours=11,
      problem="A single VOC reading cannot identify a source; a time-series with burn-in and baseline metadata can.",
      outcome="A BME680 node logs raw gas resistance with a rolling baseline and flags short-term deviations with timestamps.",
      objectives="Interpret raw gas resistance, not an unlicensed IAQ index|Track a slow clean-air baseline|Log events with RTC timestamps",
      use_cases="Kitchen ventilation study|Solvent storage monitor|Indoor chemistry lesson",
      algorithm="Log-ratio of gas resistance to a rolling baseline detects VOC events; a 3-sample confirmation avoids single-sample spikes.",
      logic="""static float base = gas_kohm;
base = base * 0.995F + gas_kohm * 0.005F;
float ratio = base / fmaxf(gas_kohm, 0.01F);
static uint8_t hits = 0;
if (ratio > 1.6F) { if (hits < 3) hits++; } else hits = 0;
char buf[220];
snprintf(buf, sizeof(buf), "{\\"ts\\":\\"%s\\",\\"gas_kohm\\":%.1f,\\"baseline_kohm\\":%.1f,\\"ratio\\":%.2f,\\"event\\":%s}", timestamp, gas_kohm, base, ratio, hits >= 3 ? "true":"false");
payload = String(buf); logLine = payload;""",
      tests="Expose the sensor to a mild vapour and confirm an event after 3 samples|Verify the baseline is slow-moving|Confirm the log contains a timestamp for every row",
      fails="Gas resistance drifts constantly | Allow 48 h burn-in and track temperature/humidity.|Heater current causes resets | Stabilise the 3.3 V rail with 100 µF.|False IAQ claims | Keep the payload as raw gas resistance with a baseline."),

    S("wildfire-smoke-mapper", "Mobile Wildfire Smoke Plume Mapper", "Air Quality Monitoring", "Advanced",
      "esp32", ["gas_mq2", "pms5003", "gps", "gsm"], "gsm", hours=18, advanced=True,
      problem="Smoke plume mapping needs geotagged particulate and gas readings from a moving platform with cellular backhaul.",
      outcome="A vehicle-mounted node streams geotagged PM2.5, smoke index and coordinates at 10 s intervals with a quality flag.",
      objectives="Geotag air-quality measurements|Transmit over cellular while moving|Flag GPS-fix quality in the payload",
      use_cases="Fire-research transect|Urban smoke survey|Environmental field course",
      algorithm="Each record combines gps.location.isValid() status, a median-filtered PM2.5 and an MQ-2 relative index; invalid fixes are tagged.",
      logic="""static float pmFilt = pm25;
pmFilt = pmFilt * 0.7F + pm25 * 0.3F;
char buf[240];
snprintf(buf, sizeof(buf), "{\\"lat\\":%.6f,\\"lng\\":%.6f,\\"pm25\\":%.1f,\\"pm25_f\\":%.1f,\\"smoke_idx\\":%.1f,\\"fix_valid\\":true}", lat, lng, pm25, pmFilt, gas_index);
payload = String(buf);""",
      tests="Drive a short transect and confirm coordinates change|Compare PM spikes with visible smoke sources|Confirm the payload is flagged when the GPS fix is lost",
      fails="GPS fix lost in vehicle | Use an external active antenna on the roof.|MQ-2 cross-sensitivity | Treat the smoke index as relative and log humidity.|Cellular dropouts | Buffer records locally and upload in batches."),
]
