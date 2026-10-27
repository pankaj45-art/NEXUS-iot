"""Canonical exact-pin circuit graph, curated definitions, rules and firmware.

This is a connection-level editor, not SPICE/PCB CAD. Only documented supported
breakouts are assigned pins. Part IDs and pin IDs are exact; positions are purely
visual. Wires, wiring tables, rules and managed firmware constants all read this
same graph. No rule pass is a safety certification or physical-test result.
"""
from __future__ import annotations
import copy
import hashlib
import html
import json
import re
from collections import defaultdict
from .. import hardware
from ..errors import ApiError

SCHEMA = 'nexus.circuit/1'


def pin(id, type='passive', *, voltage=None, required=True, direction='bidirectional'):
    return dict(id=id, type=type, voltage=voltage, required=required, direction=direction)


def part(name, pins, ref, *, voltage=3.3, current=None, notes='', iface='discrete', driver=None):
    return dict(name=name, pins=pins, reference=ref, supply_v=voltage,
                current_ma=current, notes=notes, interface=iface, driver=driver,
                compatible_boards=['esp32', 'esp32s3'], reviewed=True,
                verification='Catalog/static review only; confirm exact breakout revision and terminals.')

CATALOG = {
 'supply5': part('5 V current-limited supply', [pin('5V','power_out',voltage=5),pin('GND','ground',voltage=0)],
                 'https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html', voltage=5, current=1000,
                 notes='Assumed 5 V / 1 A protected bench supply. Confirm motor stall current and fusing. Avoid USB/external-power backfeed.'),
 'soil_cap': part('Capacitive soil moisture v1.2 breakout', [pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('AO','analog_out',voltage=3.3)],
                  'https://wiki.dfrobot.com/Capacitive_Soil_Moisture_Sensor_SKU_SEN0193',current=5,iface='analog',driver='soil',
                  notes='Assumes a 3.3 V compatible analog breakout; clones vary. Measure AO maximum before connection. Keep PCB connector dry.'),
 'gas_mq2': part('MQ-2 analog module (educational)', [pin('VCC','power_in',voltage=5),pin('GND','ground',voltage=0),pin('AO','analog_out',voltage=5),pin('DO','digital_out',voltage=5,required=False)],
                 'https://www.winsen-sensor.com/sensors/combustible-gas-sensor/mq-2.html',voltage=5,current=180,iface='analog',driver='gas',
                 notes='AO requires a divider before a 3.3 V ADC. Heater needs warm-up. NO life-safety alarm, no flammable-gas release test; raw index only, not calibrated ppm.'),
 'bme280': part('BME280 3.3 V I2C breakout', [pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('SDA','i2c_sda',voltage=3.3),pin('SCL','i2c_scl',voltage=3.3)],
                'https://www.bosch-sensortec.com/products/environmental-sensors/humidity-sensors-bme280/',current=1,iface='i2c',driver='bme280',
                notes='Assume address 0x76; verify breakout address/pull-ups and 3.3 V bus. Never pull the bus up to 5 V.'),
 'dht22': part('DHT22 / AM2302', [pin('VCC','power_in',voltage=3.3),pin('DATA','digital_io',voltage=3.3),pin('GND','ground',voltage=0)],
               'https://learn.adafruit.com/dht',current=3,iface='onewire',driver='dht22',
               notes='Signals are named terminals, not package lead numbers. Confirm front/back package orientation. A 4.7 kΩ DATA pull-up is required unless fitted to the module.'),
 'mosfet': part('AO3400A N-channel MOSFET', [pin('G','gate',voltage=3.3),pin('D','drain'),pin('S','source')],
                'https://aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a',voltage=5,driver='switch',
                notes='Named schematic terminals: SOT23 pins 1=G, 2=S, 3=D; verify manufacturer package drawing and thermal/current rating. Gate resistor/pulldown and inductive flyback path required.'),
 'pump': part('Low-voltage 5 V pump', [pin('+','power_in',voltage=5),pin('-','load_return')],
              'https://learn.adafruit.com/adafruit-motor-selection-guide',voltage=5,current=250,
              notes='250 mA running-current assumption only. Stall/inrush unknown; select protected supply/diode/MOSFET after measuring. Never drive from GPIO.'),
 'buzzer': part('3.3 V active buzzer module', [pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('SIG','digital_in',voltage=3.3)],
                'https://learn.adafruit.com/using-piezo-buzzers-with-circuitpython-arduino',current=5,driver='buzzer',
                notes='Assumes a module with a logic input and onboard driver, NOT a bare high-current buzzer. Confirm input load <= 2 mA.'),
 'led': part('Indicator LED', [pin('A','led_anode'),pin('K','led_cathode')],
             'https://docs.arduino.cc/built-in-examples/basics/Blink',driver='led',notes='Always use a current-limiting series resistor (220 Ω at 3.3 V is a typical starting point).'),
 'r220': part('220 Ω series resistor',[pin('1'),pin('2')],'https://docs.arduino.cc/built-in-examples/basics/Blink',voltage=None),
 'r100': part('100 Ω gate resistor',[pin('1'),pin('2')],'https://aosmd.com/products/mosfets/low-voltage-mosfets-12v-30v/ao3400a',voltage=None),
 'r4k7': part('4.7 kΩ pull-up',[pin('1'),pin('2')],'https://learn.adafruit.com/dht',voltage=None),
 'r10k': part('10 kΩ resistor',[pin('1'),pin('2')],'https://learn.sparkfun.com/tutorials/voltage-dividers/all',voltage=None),
 'r15k': part('15 kΩ divider resistor',[pin('1'),pin('2')],'https://learn.sparkfun.com/tutorials/voltage-dividers/all',voltage=None),
 'diode': part('SS14 Schottky flyback diode',[pin('A','diode_anode'),pin('K','diode_cathode')],
               'https://www.vishay.com/docs/88746/ss12.pdf',voltage=None,
               notes='Stripe is cathode K; reverse-biased across load during normal operation. Check reverse voltage and surge current against actual motor.'),
 # Expanded exact-terminal library. Electrical compatibility depends on the exact breakout/revision.
 'hcsr04': part('HC-SR04 ultrasonic distance module',[pin('VCC','power_in',voltage=5),pin('TRIG','digital_in',voltage=3.3),pin('ECHO','digital_out',voltage=5),pin('GND','ground',voltage=0)],'https://www.sparkfun.com/products/15569',voltage=5,current=15,iface='digital',notes='ECHO is typically 5 V; use a resistor divider/level shifter before ESP32 GPIO. Clone pinouts and range vary.'),
 'pir': part('HC-SR501 PIR motion sensor',[pin('VCC','power_in',voltage=5),pin('OUT','digital_out',voltage=3.3),pin('GND','ground',voltage=0)],'https://learn.adafruit.com/pir-passive-infrared-proximity-motion-sensor',voltage=5,current=65,iface='digital',notes='Allow warm-up; adjust delay/sensitivity. Confirm the specific module supply and output specifications.'),
 'relay1': part('Single-channel 5 V relay module',[pin('VCC','power_in',voltage=5),pin('GND','ground',voltage=0),pin('IN','digital_in',voltage=3.3),pin('COM'),pin('NO'),pin('NC')],'https://docs.arduino.cc/learn/electronics/relay-basics/',voltage=5,current=80,iface='digital',notes='Trigger polarity and input current vary by module. Use low-voltage DC only for beginner builds; mains requires rated enclosure, isolation, fuse and qualified supervision.'),
 'servo_sg90': part('SG90 micro servo',[pin('V+','power_in',voltage=5),pin('GND','ground',voltage=0),pin('SIG','digital_in',voltage=3.3)],'https://learn.adafruit.com/adafruit-arduino-lesson-14-servo-motors',voltage=5,current=500,iface='pwm',notes='Use a separate regulated 5 V supply sized for stall current and share signal ground; never power servo from GPIO.'),
 'oled_ssd1306': part('SSD1306 0.96-inch I2C OLED breakout',[pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('SDA','i2c_sda',voltage=3.3),pin('SCL','i2c_scl',voltage=3.3)],'https://learn.adafruit.com/monochrome-oled-breakouts',voltage=3.3,current=25,iface='i2c',notes='Check breakout supply range and I2C address (commonly 0x3C or 0x3D).'),
 'mpu6050': part('MPU-6050 6-axis IMU breakout',[pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('SDA','i2c_sda',voltage=3.3),pin('SCL','i2c_scl',voltage=3.3),pin('INT','digital_out',voltage=3.3,required=False)],'https://invensense.tdk.com/products/motion-tracking/6-axis/mpu-6050/',voltage=3.3,current=4,iface='i2c',notes='Bare IC is not 5 V tolerant; breakout regulators/level shifting differ. Confirm board revision.'),
 'ds3231': part('DS3231 RTC module',[pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('SDA','i2c_sda',voltage=3.3),pin('SCL','i2c_scl',voltage=3.3),pin('SQW','digital_out',voltage=3.3,required=False)],'https://www.analog.com/en/products/ds3231.html',voltage=3.3,current=2,iface='i2c',notes='Some modules pull I2C up to VCC; avoid 5 V pull-ups on ESP32. Battery type and charging circuit must match module.'),
 'bh1750': part('BH1750 ambient light sensor',[pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('SDA','i2c_sda',voltage=3.3),pin('SCL','i2c_scl',voltage=3.3)],'https://www.rohm.com/products/sensors/optical/light-sensors/bh1750',voltage=3.3,current=1,iface='i2c',notes='Check breakout voltage and address, commonly 0x23 or 0x5C.'),
 'sound_analog': part('Analog sound sensor module',[pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('AO','analog_out',voltage=3.3),pin('DO','digital_out',voltage=3.3,required=False)],'https://docs.arduino.cc/learn/electronics/analog-input/',voltage=3.3,current=5,iface='analog',notes='Module sensitivity and output range vary; not a calibrated sound-level meter.'),
 'rain_sensor': part('Rain / water detection module',[pin('VCC','power_in',voltage=3.3),pin('GND','ground',voltage=0),pin('AO','analog_out',voltage=3.3),pin('DO','digital_out',voltage=3.3,required=False)],'https://docs.arduino.cc/learn/electronics/analog-input/',voltage=3.3,current=10,iface='analog',notes='Plate corrosion is common; use short powered measurements and verify analog output voltage.'),
 'push_button': part('Momentary push button',[pin('1'),pin('2')],'https://docs.arduino.cc/built-in-examples/digital/Button/',voltage=None,iface='discrete',notes='Use INPUT_PULLUP or a suitable external pull-up/down; button contact orientation depends on package.'),
 'potentiometer': part('10 kΩ potentiometer',[pin('END1'),pin('WIPER','analog_out',voltage=3.3),pin('END2')],'https://docs.arduino.cc/learn/electronics/potentiometer-basics/',voltage=3.3,iface='analog',notes='Connect ends to 3V3 and GND; wiper to ADC. Do not connect ADC wiper to a voltage above board ADC limit.'),
 'breadboard': part('Solderless breadboard',[pin('RAIL+'),pin('RAIL-'),pin('ROWS')],'https://learn.sparkfun.com/tutorials/how-to-use-a-breadboard/all',voltage=None,iface='passive',notes='Internal strip layout varies; verify rails and row continuity. Never use for mains or high-current loads.'),
 'jumper_wires': part('Male-female jumper wire set',[pin('END1'),pin('END2')],'https://learn.sparkfun.com/tutorials/how-to-use-a-breadboard/all',voltage=None,iface='passive',notes='Wire gauge, length and connector gender must match the physical modules.'),
 'cap10u': part('10 µF decoupling capacitor',[pin('+','power_in'),pin('-','ground')],'https://www.analog.com/en/resources/technical-articles/understanding-decoupling-capacitors.html',voltage=None,iface='passive',notes='Observe electrolytic polarity and voltage rating; place near module supply as recommended by datasheet.'),
 'cap100n': part('100 nF ceramic decoupling capacitor',[pin('1'),pin('2')],'https://www.analog.com/en/resources/technical-articles/understanding-decoupling-capacitors.html',voltage=None,iface='passive',notes='Place near IC supply pins when recommended by manufacturer.'),
 'battery18650': part('Single-cell 18650 Li-ion battery (protected holder required)',[pin('+','power_out',voltage=3.7),pin('-','ground',voltage=0)],'https://www.analog.com/en/resources/technical-articles/a-designers-guide-to-lithium-ion-li-ion-battery-management.html',voltage=3.7,current=None,iface='power',notes='Requires appropriate protection, charging and regulation. Do not charge a bare cell without a matched charger/protection circuit.'),
}

# Expanded practical prototype library. Generic planning parts are explicitly marked
# and must be replaced with exact manufacturer/model data before build verification.
CATALOG.update({
    'dht11': part('DHT11 temperature/humidity module', [pin('VCC', 'power_in', voltage=3.3), pin('DATA', 'digital_io', voltage=3.3), pin('GND', 'ground', voltage=0)], 'https://learn.adafruit.com/dht', voltage=3.3, current=3, iface='onewire', driver='dht11', notes='Check breakout pin order and pull-up; low-cost, lower accuracy than DHT22.'),
    'ds18b20': part('DS18B20 temperature sensor', [pin('VDD', 'power_in', voltage=3.3), pin('DQ', 'digital_io', voltage=3.3), pin('GND', 'ground', voltage=0)], 'https://www.analog.com/en/products/ds18b20.html', voltage=3.3, current=2, iface='onewire', driver='ds18b20', notes='Bare sensor needs a pull-up on DQ; waterproof probe cable colors vary.'),
    'ldr': part('Photoresistor (LDR)', [pin('END1', 'passive', voltage=None), pin('END2', 'passive', voltage=None)], 'https://docs.arduino.cc/learn/electronics/analog-input/', voltage=None, current=0, iface='analog', driver='ldr', notes='Requires a resistor divider; calculate ADC voltage and resistor value for desired range.'),
    'ir_obstacle': part('IR obstacle detection module', [pin('VCC', 'power_in', voltage=3.3), pin('OUT', 'digital_out', voltage=3.3), pin('GND', 'ground', voltage=0)], 'https://docs.arduino.cc/learn/electronics/', voltage=3.3, current=20, iface='digital', driver='digital', notes='Output polarity and operating voltage vary by module; verify the exact board.'),
    'ir_receiver': part('38 kHz IR receiver module', [pin('VCC', 'power_in', voltage=3.3), pin('OUT', 'digital_out', voltage=3.3), pin('GND', 'ground', voltage=0)], 'https://github.com/Arduino-IRremote/Arduino-IRremote', voltage=3.3, current=2, iface='digital', driver='ir', notes='Pin order varies by package; use the manufacturer pinout.'),
    'ir_led': part('IR LED emitter', [pin('A', 'led_anode'), pin('K', 'led_cathode')], 'https://docs.arduino.cc/', voltage=None, current=20, iface='discrete', driver=None, notes='Use a calculated current-limiting resistor and transistor driver when current exceeds GPIO limits.'),
    'flame_sensor': part('Flame sensor module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=3.3), pin('DO', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/learn/electronics/analog-input/', voltage=3.3, current=15, iface='analog', driver='analog', notes='Educational detector only; never use as a certified fire safety device.'),
    'water_level': part('Water level sensor strip', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SIG', 'analog_out', voltage=3.3)], 'https://docs.arduino.cc/learn/electronics/analog-input/', voltage=3.3, current=10, iface='analog', driver='analog', notes='Corrosion and conductive-water variation affect readings; power intermittently where practical.'),
    'float_switch': part('Float level switch', [pin('COM', 'passive'), pin('NO', 'passive'), pin('NC', 'passive')], 'https://docs.arduino.cc/', voltage=None, current=0, iface='discrete', driver=None, notes='Check whether the selected float switch is normally open or closed in the installed orientation.'),
    'load_cell_hx711': part('Load cell + HX711 amplifier', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('DT', 'digital_out', voltage=3.3), pin('SCK', 'digital_in', voltage=3.3)], 'https://github.com/bogde/HX711', voltage=3.3, current=5, iface='digital', driver='hx711', notes='Load cell wiring/color codes vary; calibrate with known weights.'),
    'max30102': part('MAX30102 pulse/SpO2 sensor breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('INT', 'digital_out', voltage=3.3)], 'https://www.analog.com/en/products/max30102.html', voltage=3.3, current=10, iface='i2c', driver='max30102', notes='Not a medical device; breakout voltage regulation varies.'),
    'gps_neo6m': part('NEO-6M GPS breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('TX', 'uart_tx', voltage=3.3), pin('RX', 'uart_rx', voltage=3.3)], 'https://www.u-blox.com/en/product/neo-6-series', voltage=3.3, current=45, iface='uart', driver='gps', notes='UART pins cross: module TX to MCU RX; verify breakout input voltage.'),
    'sim800l': part('SIM800L GSM/GPRS module', [pin('VBAT', 'power_in', voltage=4.0), pin('GND', 'ground', voltage=0), pin('TXD', 'uart_tx', voltage=2.8), pin('RXD', 'uart_rx', voltage=2.8)], 'https://www.simcom.com/', voltage=4.0, current=2000, iface='uart', driver=None, notes='Requires ~4 V supply with high burst current; do not power from board 3V3. Check cellular band/operator availability.'),
    'nrf24l01': part('nRF24L01+ 2.4 GHz transceiver', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('CE', 'digital_in', voltage=3.3), pin('CSN', 'digital_in', voltage=3.3), pin('SCK', 'spi_sck', voltage=3.3), pin('MOSI', 'spi_mosi', voltage=3.3), pin('MISO', 'spi_miso', voltage=3.3), pin('IRQ', 'digital_out', voltage=3.3)], 'https://www.nordicsemi.com/Products/nRF24-series', voltage=3.3, current=15, iface='spi', driver=None, notes='3.3 V only; add local decoupling. PA/LNA variants need a suitable supply.'),
    'rfid_rc522': part('MFRC522 RFID reader', [pin('3V3', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA_CS', 'spi_cs', voltage=3.3), pin('SCK', 'spi_sck', voltage=3.3), pin('MOSI', 'spi_mosi', voltage=3.3), pin('MISO', 'spi_miso', voltage=3.3), pin('RST', 'digital_in', voltage=3.3), pin('IRQ', 'digital_out', voltage=3.3)], 'https://github.com/miguelbalboa/rfid', voltage=3.3, current=26, iface='spi', driver=None, notes='Use 3.3 V logic; library and board pin labels vary. Not a secure access-control system by itself.'),
    'sd_card_spi': part('MicroSD SPI breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('CS', 'spi_cs', voltage=3.3), pin('SCK', 'spi_sck', voltage=3.3), pin('MOSI', 'spi_mosi', voltage=3.3), pin('MISO', 'spi_miso', voltage=3.3)], 'https://docs.arduino.cc/libraries/sd/', voltage=3.3, current=100, iface='spi', driver=None, notes='Card current peaks can be significant; use a breakout designed for 3.3 V logic and FAT-compatible card.'),
    'max7219_8x8': part('MAX7219 8x8 LED matrix', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('DIN', 'spi_mosi', voltage=5), pin('CLK', 'spi_sck', voltage=5), pin('CS', 'spi_cs', voltage=5)], 'https://docs.arduino.cc/', voltage=5, current=200, iface='spi', driver=None, notes='Check 3.3 V logic compatibility on the chosen breakout; use level shifting if required.'),
    'ws2812_strip': part('WS2812B addressable LED strip segment', [pin('5V', 'power_in', voltage=5), pin('DIN', 'digital_in', voltage=5), pin('GND', 'ground', voltage=0)], 'https://learn.adafruit.com/adafruit-neopixel-uberguide', voltage=5, current=1000, iface='digital', driver=None, notes='Budget up to ~60 mA per RGB pixel at full white; use external supply, common ground, data resistor and bulk capacitor.'),
    'lcd1602_i2c': part('1602 character LCD with I2C backpack', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=5), pin('SCL', 'i2c_scl', voltage=5)], 'https://docs.arduino.cc/', voltage=5, current=30, iface='i2c', driver=None, notes='Many backpacks pull I2C to 5 V; use a 3.3 V-safe backpack or bidirectional level shifter.'),
    'tm1637': part('TM1637 four-digit display', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('CLK', 'digital_io', voltage=3.3), pin('DIO', 'digital_io', voltage=3.3)], 'https://github.com/avishorp/TM1637', voltage=5, current=30, iface='digital', driver=None, notes='Confirm the selected module accepts 3.3 V logic and board supply.'),
    'stepper_28byj48': part('28BYJ-48 stepper motor + ULN2003 driver', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('IN1', 'digital_in', voltage=3.3), pin('IN2', 'digital_in', voltage=3.3), pin('IN3', 'digital_in', voltage=3.3), pin('IN4', 'digital_in', voltage=3.3)], 'https://docs.arduino.cc/', voltage=5, current=240, iface='digital', driver=None, notes='Power motor from a suitable external supply; verify coil current and driver board.'),
    'motor_driver_l298n': part('L298N dual H-bridge driver module', [pin('VS', 'power_in', voltage=12), pin('5V_LOGIC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('ENA', 'pwm_in', voltage=3.3), pin('IN1', 'digital_in', voltage=3.3), pin('IN2', 'digital_in', voltage=3.3), pin('ENB', 'pwm_in', voltage=3.3), pin('IN3', 'digital_in', voltage=3.3), pin('IN4', 'digital_in', voltage=3.3), pin('OUT1', 'load_out'), pin('OUT2', 'load_out'), pin('OUT3', 'load_out'), pin('OUT4', 'load_out')], 'https://www.st.com/en/motor-drivers/l298.html', voltage=12, current=1000, iface='motor', driver=None, notes='High voltage drop and heating; check module jumper configuration, current limits and motor stall current.'),
    'motor_driver_tb6612': part('TB6612FNG dual motor driver', [pin('VM', 'power_in', voltage=6), pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('PWMA', 'pwm_in', voltage=3.3), pin('AIN1', 'digital_in', voltage=3.3), pin('AIN2', 'digital_in', voltage=3.3), pin('PWMB', 'pwm_in', voltage=3.3), pin('BIN1', 'digital_in', voltage=3.3), pin('BIN2', 'digital_in', voltage=3.3), pin('STBY', 'digital_in', voltage=3.3), pin('AO1', 'load_out'), pin('AO2', 'load_out'), pin('BO1', 'load_out'), pin('BO2', 'load_out')], 'https://toshiba.semicon-storage.com/', voltage=6, current=1000, iface='motor', driver=None, notes='Check thermal and peak current limits; motor supply and logic supply are separate.'),
    'dc_motor': part('Brushed DC motor (low-voltage)', [pin('M+', 'load_in'), pin('M-', 'load_in')], 'https://learn.adafruit.com/adafruit-arduino-lesson-13-dc-motors', voltage=6, current=500, iface='motor', driver=None, notes='Never connect directly to GPIO; use a rated driver, suppression and external supply. Current is load-dependent.'),
    'fan5v': part('5 V brushless fan', [pin('+5V', 'power_in', voltage=5), pin('GND', 'ground', voltage=0)], 'https://learn.adafruit.com/', voltage=5, current=250, iface='power', driver=None, notes='Check startup current and connector pinout; switch with a rated transistor/MOSFET if controlled.'),
    'buzzer_passive': part('Passive piezo buzzer', [pin('A', 'signal_in'), pin('K', 'ground')], 'https://docs.arduino.cc/', voltage=3.3, current=10, iface='pwm', driver=None, notes='Use PWM/tone generation; use a transistor if current exceeds GPIO rating.'),
    'mosfet_module': part('Logic-level MOSFET switch module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SIG', 'digital_in', voltage=3.3), pin('LOAD+', 'load_out'), pin('LOAD-', 'load_out')], 'https://learn.sparkfun.com/tutorials/transistors/all', voltage=3.3, current=10, iface='digital', driver=None, notes='Verify MOSFET part, polarity, gate drive and load rating; inductive loads require a flyback path.'),
    'bjt_npn': part('NPN transistor (2N2222-class)', [pin('B', 'gate', voltage=3.3), pin('C', 'load_out'), pin('E', 'ground', voltage=0)], 'https://learn.sparkfun.com/tutorials/transistors/all', voltage=None, current=100, iface='discrete', driver=None, notes='Use a base resistor; pinout differs by manufacturer/package. Add flyback diode for inductive loads.'),
    'diode_1n4007': part('1N4007 rectifier diode', [pin('A', 'diode_anode'), pin('K', 'diode_cathode')], 'https://www.vishay.com/', voltage=None, current=1000, iface='discrete', driver=None, notes='Stripe marks cathode; verify reverse voltage and surge/current suitability.'),
    'zener_3v3': part('3.3 V Zener diode', [pin('A', 'diode_anode'), pin('K', 'diode_cathode')], 'https://www.onsemi.com/', voltage=None, current=5, iface='discrete', driver=None, notes='Not a substitute for a regulator without resistor and power calculations.'),
    'r1k': part('1 kΩ resistor', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Check power dissipation and tolerance for the circuit.'),
    'r47k': part('47 kΩ resistor', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Check tolerance and divider/loading effects.'),
    'r100k': part('100 kΩ resistor', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Check tolerance, leakage and ADC source impedance.'),
    'cap1u': part('1 µF capacitor', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.analog.com/', voltage=None, current=0, iface='passive', driver=None, notes='Voltage rating and polarity depend on capacitor type; ceramic capacitors are typically non-polarized.'),
    'cap100u': part('100 µF electrolytic capacitor', [pin('+', 'power_in'), pin('-', 'ground')], 'https://www.analog.com/', voltage=None, current=0, iface='passive', driver=None, notes='Observe polarity and voltage rating; useful for supply transients when correctly selected.'),
    'inductor': part('Inductor (value must be selected)', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Inductance, saturation current and DCR must be selected for the actual converter/filter.'),
    'fuse': part('Inline fuse and holder', [pin('IN', 'power_in'), pin('OUT', 'power_out')], 'https://www.littelfuse.com/', voltage=None, current=0, iface='power', driver=None, notes='Select fuse rating, breaking capacity and wire rating based on measured load and supply.'),
    'buck_adjustable': part('Adjustable DC-DC buck converter', [pin('VIN+', 'power_in'), pin('VIN-', 'ground'), pin('VOUT+', 'power_out'), pin('VOUT-', 'ground')], 'https://www.ti.com/power-management/', voltage=24, current=1000, iface='power', driver=None, notes='Set and measure output before connecting electronics; verify input range, output current and thermal limits.'),
    'boost_converter': part('DC-DC boost converter', [pin('VIN+', 'power_in'), pin('VIN-', 'ground'), pin('VOUT+', 'power_out'), pin('VOUT-', 'ground')], 'https://www.ti.com/power-management/', voltage=5, current=500, iface='power', driver=None, notes='Output current falls as voltage is boosted; verify input/output limits and efficiency.'),
    'charger_tp4056': part('TP4056 single-cell Li-ion charger module', [pin('IN+', 'power_in', voltage=5), pin('IN-', 'ground', voltage=0), pin('BAT+', 'power_out', voltage=4.2), pin('BAT-', 'ground', voltage=0)], 'https://www.mikrocontroller.net/', voltage=5, current=1000, iface='power', driver=None, notes='Use only with compatible single-cell Li-ion chemistry; protection varies by board. Never charge unattended or use damaged cells.'),
    'battery_holder_18650': part('18650 cell holder (single cell)', [pin('+', 'power_out', voltage=3.7), pin('-', 'ground', voltage=0)], 'https://www.analog.com/', voltage=3.7, current=0, iface='power', driver=None, notes='Holder provides no cell protection; use a protected cell or protection circuit and matched charger.'),
    'terminal_block': part('2-pin screw terminal block', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Match pitch, wire gauge and current rating; tighten safely.'),
    'jst_ph2': part('JST-PH 2-pin cable/connector', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.jst.com/', voltage=None, current=0, iface='passive', driver=None, notes='Confirm polarity and pitch; connector wire colors are not guaranteed.'),
    'level_shifter_4ch': part('4-channel bidirectional logic-level shifter', [pin('LV', 'power_in', voltage=3.3), pin('HV', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('LV1', 'digital_io', voltage=3.3), pin('LV2', 'digital_io', voltage=3.3), pin('LV3', 'digital_io', voltage=3.3), pin('LV4', 'digital_io', voltage=3.3), pin('HV1', 'digital_io', voltage=5), pin('HV2', 'digital_io', voltage=5), pin('HV3', 'digital_io', voltage=5), pin('HV4', 'digital_io', voltage=5)], 'https://learn.sparkfun.com/tutorials/logic-level-converter-hookup-guide/all', voltage=5, current=10, iface='interface', driver=None, notes='Connect both reference rails and ground; verify direction/speed suitability for the signal.'),
    'opamp_lm358': part('LM358 op-amp IC/module', [pin('VCC+', 'power_in'), pin('VCC-', 'ground'), pin('IN+', 'analog_in'), pin('IN-', 'analog_in'), pin('OUT', 'analog_out')], 'https://www.ti.com/product/LM358', voltage=5, current=2, iface='analog', driver=None, notes='Check supply range, input common-mode range, output swing and pinout. Not rail-to-rail on all parameters.'),
    'comparator_lm393': part('LM393 comparator module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('IN+', 'analog_in'), pin('IN-', 'analog_in'), pin('OUT', 'digital_out', voltage=3.3)], 'https://www.ti.com/product/LM393', voltage=5, current=2, iface='analog', driver=None, notes='Open-collector output needs a pull-up; confirm module pull-up voltage to protect 3.3 V GPIO.'),
    'ads1115': part('ADS1115 16-bit ADC breakout', [pin('VDD', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('A0', 'analog_in'), pin('A1', 'analog_in'), pin('A2', 'analog_in'), pin('A3', 'analog_in'), pin('ALERT', 'digital_out', voltage=3.3)], 'https://www.ti.com/product/ADS1115', voltage=3.3, current=1, iface='i2c', driver=None, notes='Analog inputs must stay within selected PGA and supply limits; verify breakout pull-ups and address.'),
    'ina219': part('INA219 current/voltage sensor', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('VIN+', 'power_in'), pin('VIN-', 'power_out')], 'https://www.ti.com/product/INA219', voltage=3.3, current=1, iface='i2c', driver=None, notes='Shunt rating and bus voltage depend on breakout; current direction follows VIN+ to VIN-.'),
    'rtc_pcf8523': part('PCF8523 RTC breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('INT', 'digital_out', voltage=3.3)], 'https://www.nxp.com/', voltage=3.3, current=1, iface='i2c', driver=None, notes='Check board voltage, battery chemistry and I2C pull-up voltage.'),
    'eeprom_24c256': part('24LC256 I2C EEPROM', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('WP', 'digital_in', voltage=3.3), pin('A0', 'ground'), pin('A1', 'ground'), pin('A2', 'ground')], 'https://www.microchip.com/', voltage=3.3, current=1, iface='i2c', driver=None, notes='Address pins must be tied to a defined logic level; ensure bus pull-ups are correct.'),
    'can_transceiver': part('CAN bus transceiver module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('TXD', 'digital_in', voltage=3.3), pin('RXD', 'digital_out', voltage=3.3), pin('CANH', 'bus'), pin('CANL', 'bus')], 'https://www.ti.com/interface/can-lin/overview.html', voltage=3.3, current=50, iface='bus', driver=None, notes='Requires a CAN controller and correctly placed termination; never confuse CAN transceiver with controller.'),
    'rs485_module': part('RS-485 transceiver module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('DI', 'uart_tx', voltage=3.3), pin('RO', 'uart_rx', voltage=3.3), pin('DE', 'digital_in', voltage=3.3), pin('/RE', 'digital_in', voltage=3.3), pin('A', 'bus'), pin('B', 'bus')], 'https://www.ti.com/interface/rs-485/overview.html', voltage=5, current=50, iface='uart', driver=None, notes='Confirm logic compatibility, A/B polarity convention, termination and biasing for cable topology.'),
    'ethernet_w5500': part('W5500 Ethernet SPI module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SCS', 'spi_cs', voltage=3.3), pin('SCLK', 'spi_sck', voltage=3.3), pin('MOSI', 'spi_mosi', voltage=3.3), pin('MISO', 'spi_miso', voltage=3.3), pin('RST', 'digital_in', voltage=3.3), pin('INT', 'digital_out', voltage=3.3)], 'https://docs.wiznet.io/', voltage=3.3, current=130, iface='spi', driver=None, notes='Use correct 3.3 V module and stable supply; magnetics/RJ45 integration varies.'),
    'bluetooth_hc05': part('HC-05 Bluetooth serial module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('TXD', 'uart_tx', voltage=3.3), pin('RXD', 'uart_rx', voltage=3.3), pin('KEY', 'digital_in', voltage=3.3), pin('STATE', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=5, current=50, iface='uart', driver=None, notes='Module RX may not be 5 V tolerant; use a divider/level shifter. Classic Bluetooth support varies by host.'),
    'wifi_esp01': part('ESP-01 ESP8266 Wi-Fi module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('TX', 'uart_tx', voltage=3.3), pin('RX', 'uart_rx', voltage=3.3), pin('EN', 'digital_in', voltage=3.3), pin('RST', 'digital_in', voltage=3.3), pin('GPIO0', 'digital_io', voltage=3.3), pin('GPIO2', 'digital_io', voltage=3.3)], 'https://docs.espressif.com/projects/esp8266/', voltage=3.3, current=300, iface='uart', driver=None, notes='Needs a stable 3.3 V supply with burst current capacity and correct boot strap levels.'),
    'relay_2ch': part('Dual-channel relay module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('IN1', 'digital_in', voltage=3.3), pin('IN2', 'digital_in', voltage=3.3), pin('COM1', 'passive'), pin('NO1', 'passive'), pin('NC1', 'passive'), pin('COM2', 'passive'), pin('NO2', 'passive'), pin('NC2', 'passive')], 'https://docs.arduino.cc/learn/electronics/relay-basics/', voltage=5, current=160, iface='digital', driver=None, notes='Trigger polarity and isolation differ by module. Keep mains wiring out of breadboards; qualified enclosure/supervision required.'),
    'solenoid_12v': part('12 V solenoid actuator', [pin('+', 'power_in', voltage=12), pin('-', 'load_return')], 'https://learn.adafruit.com/', voltage=12, current=1000, iface='power', driver=None, notes='Use a rated transistor/driver and flyback diode; select supply by measured inrush and duty cycle.'),
    'pump_12v': part('12 V DC pump', [pin('+', 'power_in', voltage=12), pin('-', 'load_return')], 'https://learn.adafruit.com/', voltage=12, current=1000, iface='power', driver=None, notes='Current is model-specific; use external supply and rated driver, check stall/inrush and liquid compatibility.'),
    'waterproof_ds18b20': part('Waterproof DS18B20 probe', [pin('RED_VDD', 'power_in', voltage=3.3), pin('DATA', 'digital_io', voltage=3.3), pin('BLACK_GND', 'ground', voltage=0)], 'https://www.analog.com/en/products/ds18b20.html', voltage=3.3, current=2, iface='onewire', driver='ds18b20', notes='Wire colors are common but not guaranteed; verify probe manufacturer. DATA pull-up required.'),
    'bme680': part('BME680 environmental sensor breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('SDO', 'ground'), pin('CS', 'power_in', voltage=3.3)], 'https://www.bosch-sensortec.com/products/environmental-sensors/gas-sensors/bme680/', voltage=3.3, current=3, iface='i2c', driver=None, notes='Confirm breakout supports I2C mode and its address/pull-ups; gas resistance is not direct calibrated air-quality truth.'),
    'sgp30': part('SGP30 air quality sensor breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3)], 'https://sensirion.com/products/catalog/SGP30/', voltage=3.3, current=50, iface='i2c', driver=None, notes='Requires warm-up and baseline handling; eCO2/TVOC are estimates, not safety measurements.'),
    'ccs811': part('CCS811 air quality sensor breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('WAKE', 'digital_in', voltage=3.3), pin('INT', 'digital_out', voltage=3.3), pin('RST', 'digital_in', voltage=3.3)], 'https://www.sciosense.com/', voltage=3.3, current=30, iface='i2c', driver=None, notes='Warm-up and baseline required; eCO2/TVOC are estimates, not certified gas alarm values.'),
    'tcs34725': part('TCS34725 RGB color sensor', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('LED', 'digital_in', voltage=3.3)], 'https://ams-osram.com/', voltage=3.3, current=5, iface='i2c', driver=None, notes='Check breakout illumination LED current and I2C voltage/address.'),
    'rotary_encoder': part('Incremental rotary encoder module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('A', 'digital_out', voltage=3.3), pin('B', 'digital_out', voltage=3.3), pin('SW', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=3.3, current=10, iface='digital', driver=None, notes='Use pull-ups/debounce; signal phase and switch polarity depend on module.'),
    'reed_switch': part('Magnetic reed switch', [pin('1', 'passive'), pin('2', 'passive')], 'https://docs.arduino.cc/', voltage=None, current=0, iface='discrete', driver=None, notes='Use pull-up/down and debounce; maximum voltage/current depend on the switch rating.'),
    'hall_sensor': part('Digital Hall-effect sensor module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('OUT', 'digital_out', voltage=3.3)], 'https://www.ti.com/sensors/magnetic-sensors/overview.html', voltage=3.3, current=5, iface='digital', driver=None, notes='Output may be open-collector; verify pull-up and magnet orientation.'),
    'vibration_sw': part('SW-420 vibration switch module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('DO', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=3.3, current=10, iface='digital', driver=None, notes='Threshold is adjustable and module is not a calibrated vibration sensor.'),
    'tilt_switch': part('Ball tilt switch', [pin('1', 'passive'), pin('2', 'passive')], 'https://docs.arduino.cc/', voltage=None, current=0, iface='discrete', driver=None, notes='Use a pull-up/down and debounce; orientation and contact behavior vary.'),
    'joystick_xy': part('Two-axis joystick module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('VRX', 'analog_out', voltage=3.3), pin('VRY', 'analog_out', voltage=3.3), pin('SW', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=3.3, current=10, iface='analog', driver=None, notes='Verify center values and ADC limits; switch usually requires pull-up.'),
    'keypad_4x4': part('4x4 matrix keypad', [pin('R1', 'digital_io', voltage=3.3), pin('R2', 'digital_io', voltage=3.3), pin('R3', 'digital_io', voltage=3.3), pin('R4', 'digital_io', voltage=3.3), pin('C1', 'digital_io', voltage=3.3), pin('C2', 'digital_io', voltage=3.3), pin('C3', 'digital_io', voltage=3.3), pin('C4', 'digital_io', voltage=3.3)], 'https://docs.arduino.cc/', voltage=3.3, current=0, iface='digital', driver=None, notes='Passive matrix keypad; use scan firmware and appropriate pull-ups; check connector orientation.'),
    'oled_spi': part('SSD1306 SPI OLED breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SCLK', 'spi_sck', voltage=3.3), pin('MOSI', 'spi_mosi', voltage=3.3), pin('CS', 'spi_cs', voltage=3.3), pin('DC', 'digital_in', voltage=3.3), pin('RST', 'digital_in', voltage=3.3)], 'https://learn.adafruit.com/monochrome-oled-breakouts', voltage=3.3, current=25, iface='spi', driver=None, notes='Confirm the display controller and interface mode from the exact board; SPI and I2C versions are not interchangeable.'),
    'gps_neo8m': part('NEO-M8 GNSS breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('TX', 'uart_tx', voltage=3.3), pin('RX', 'uart_rx', voltage=3.3), pin('PPS', 'digital_out', voltage=3.3)], 'https://www.u-blox.com/', voltage=3.3, current=40, iface='uart', driver=None, notes='Verify module voltage and antenna requirements; indoor fix may be unavailable.'),
    'microphone_i2s': part('I2S digital microphone breakout', [pin('3V3', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('BCLK', 'digital_out', voltage=3.3), pin('LRCLK', 'digital_out', voltage=3.3), pin('DOUT', 'digital_out', voltage=3.3), pin('SEL', 'ground')], 'https://docs.espressif.com/projects/esp-idf/', voltage=3.3, current=5, iface='i2s', driver=None, notes='I2S pin roles depend on master/slave configuration and board support; check the exact microphone breakout.'),
    'dac_mcp4725': part('MCP4725 I2C DAC breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('VOUT', 'analog_out')], 'https://www.microchip.com/', voltage=3.3, current=1, iface='i2c', driver=None, notes='Output range is bounded by supply; check load and address jumpers.'),
    'rtc_ds1307': part('DS1307 RTC module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=5), pin('SCL', 'i2c_scl', voltage=5), pin('SQW', 'digital_out', voltage=5)], 'https://www.analog.com/', voltage=5, current=2, iface='i2c', driver=None, notes='Often has 5 V I2C pull-ups; use level shifting for ESP32 and check backup battery charging circuit.'),
    'ultrasonic_jsn': part('Waterproof ultrasonic sensor module', [pin('VCC', 'power_in', voltage=5), pin('TRIG', 'digital_in', voltage=3.3), pin('ECHO', 'digital_out', voltage=5), pin('GND', 'ground', voltage=0)], 'https://docs.arduino.cc/', voltage=5, current=30, iface='digital', driver=None, notes='Model-specific UART/PWM modes exist; verify pinout and level shift ECHO before ESP32.'),
    'pwm_driver_pca9685': part('PCA9685 16-channel PWM driver', [pin('VCC', 'power_in', voltage=3.3), pin('V+', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('OE', 'digital_in', voltage=3.3)], 'https://learn.adafruit.com/16-channel-pwm-servo-driver', voltage=5, current=10, iface='i2c', driver=None, notes='V+ powers loads separately; size servo supply and ground correctly; board address depends on jumpers.'),
    'stepper_driver_a4988': part('A4988 stepper driver module', [pin('VMOT', 'power_in', voltage=12), pin('GND_MOT', 'ground', voltage=0), pin('VDD', 'power_in', voltage=3.3), pin('GND_LOGIC', 'ground', voltage=0), pin('STEP', 'digital_in', voltage=3.3), pin('DIR', 'digital_in', voltage=3.3), pin('EN', 'digital_in', voltage=3.3), pin('MS1', 'digital_in', voltage=3.3), pin('MS2', 'digital_in', voltage=3.3), pin('MS3', 'digital_in', voltage=3.3), pin('RESET', 'digital_in', voltage=3.3), pin('SLEEP', 'digital_in', voltage=3.3), pin('1A', 'load_out'), pin('1B', 'load_out'), pin('2A', 'load_out'), pin('2B', 'load_out')], 'https://www.pololu.com/product/1182', voltage=12, current=1000, iface='motor', driver=None, notes='Set current limit before use; add bulk capacitor near VMOT; heatsinking and coil pairing matter.'),
    'ina226': part('INA226 current monitor breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SDA', 'i2c_sda', voltage=3.3), pin('SCL', 'i2c_scl', voltage=3.3), pin('VIN+', 'power_in'), pin('VIN-', 'power_out'), pin('ALERT', 'digital_out', voltage=3.3)], 'https://www.ti.com/product/INA226', voltage=3.3, current=1, iface='i2c', driver=None, notes='Shunt and bus-voltage limits depend on board design; configure calibration before trusting current readings.'),
    'thermistor_ntc': part('10 kΩ NTC thermistor', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.analog.com/', voltage=None, current=0, iface='analog', driver=None, notes='Requires divider and a calibrated beta/Steinhart-Hart model; do not assume temperature from raw ADC.'),
    'photodiode': part('Photodiode sensor', [pin('A', 'analog_out'), pin('K', 'analog_in')], 'https://www.digikey.com/', voltage=None, current=0, iface='analog', driver=None, notes='Usually requires bias/transimpedance amplifier; polarity and response depend on selected part.'),
    'electret_mic_amp': part('Electret microphone amplifier module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('OUT', 'analog_out', voltage=3.3)], 'https://learn.adafruit.com/', voltage=3.3, current=5, iface='analog', driver=None, notes='Output is not calibrated SPL; check output bias and ADC range.'),
    'waterproof_ds18b20_module': part('DS18B20 screw-terminal breakout', [pin('VCC', 'power_in', voltage=3.3), pin('DATA', 'digital_io', voltage=3.3), pin('GND', 'ground', voltage=0)], 'https://www.analog.com/en/products/ds18b20.html', voltage=3.3, current=2, iface='onewire', driver='ds18b20', notes='Confirm onboard pull-up and terminal order; use correct waterproof probe wiring.'),
    'dc_jack': part('DC barrel jack power input', [pin('CENTER', 'power_in'), pin('SLEEVE', 'ground')], 'https://www.digikey.com/', voltage=12, current=0, iface='power', driver=None, notes='Center-positive is common but not universal; confirm supply polarity and connector dimensions.'),
    'usb_uart': part('USB-to-UART adapter (3.3 V logic)', [pin('3V3', 'power_out', voltage=3.3), pin('GND', 'ground', voltage=0), pin('TXD', 'uart_tx', voltage=3.3), pin('RXD', 'uart_rx', voltage=3.3), pin('DTR', 'digital_out', voltage=3.3), pin('RTS', 'digital_out', voltage=3.3)], 'https://www.silabs.com/interface/usb-bridges', voltage=3.3, current=100, iface='uart', driver=None, notes='Ensure adapter I/O logic is 3.3 V; TX/RX cross and power output current may be limited.'),
    'esp32_cam': part('ESP32-CAM module', [pin('5V', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('U0R', 'uart_rx', voltage=3.3), pin('U0T', 'uart_tx', voltage=3.3), pin('GPIO0', 'digital_io', voltage=3.3), pin('GPIO4', 'digital_io', voltage=3.3), pin('GPIO12', 'digital_io', voltage=3.3), pin('GPIO13', 'digital_io', voltage=3.3), pin('GPIO14', 'digital_io', voltage=3.3), pin('GPIO15', 'digital_io', voltage=3.3)], 'https://docs.espressif.com/projects/esp-idf/', voltage=5, current=300, iface='board', driver=None, notes='Pin availability is constrained by camera, flash and boot strapping; use a stable supply and board-specific pin map.'),
    'raspberry_pi_header': part('Raspberry Pi 40-pin header interface', [pin('3V3', 'power_out', voltage=3.3), pin('5V', 'power_out', voltage=5), pin('GND', 'ground', voltage=0), pin('SDA1', 'i2c_sda', voltage=3.3), pin('SCL1', 'i2c_scl', voltage=3.3), pin('MOSI', 'spi_mosi', voltage=3.3), pin('MISO', 'spi_miso', voltage=3.3), pin('SCLK', 'spi_sck', voltage=3.3), pin('TXD', 'uart_tx', voltage=3.3), pin('RXD', 'uart_rx', voltage=3.3)], 'https://www.raspberrypi.com/documentation/computers/raspberry-pi.html', voltage=5, current=500, iface='board', driver=None, notes='Reference interface only; header pin numbers and current budget depend on Pi model. GPIO is 3.3 V, not 5 V tolerant.'),
    'arduino_uno_r3': part('Arduino Uno R3 board', [pin('5V', 'power_out', voltage=5), pin('3V3', 'power_out', voltage=3.3), pin('GND', 'ground', voltage=0), pin('A0', 'analog_in', voltage=5), pin('A1', 'analog_in', voltage=5), pin('A2', 'analog_in', voltage=5), pin('A3', 'analog_in', voltage=5), pin('A4_SDA', 'i2c_sda', voltage=5), pin('A5_SCL', 'i2c_scl', voltage=5), pin('D0_RX', 'uart_rx', voltage=5), pin('D1_TX', 'uart_tx', voltage=5), pin('D2', 'digital_io', voltage=5), pin('D3_PWM', 'pwm_in', voltage=5), pin('D4', 'digital_io', voltage=5), pin('D5_PWM', 'pwm_in', voltage=5), pin('D6_PWM', 'pwm_in', voltage=5), pin('D7', 'digital_io', voltage=5), pin('D8', 'digital_io', voltage=5), pin('D9_PWM', 'pwm_in', voltage=5), pin('D10_CS', 'spi_cs', voltage=5), pin('D11_MOSI', 'spi_mosi', voltage=5), pin('D12_MISO', 'spi_miso', voltage=5), pin('D13_SCK', 'spi_sck', voltage=5)], 'https://docs.arduino.cc/hardware/uno-rev3', voltage=5, current=200, iface='board', driver=None, notes='Board definition is for reference wiring only; current limits and 5 V logic compatibility differ from ESP32.'),
    'arduino_nano': part('Arduino Nano classic board', [pin('5V', 'power_out', voltage=5), pin('3V3', 'power_out', voltage=3.3), pin('GND', 'ground', voltage=0), pin('A0', 'analog_in', voltage=5), pin('A1', 'analog_in', voltage=5), pin('A2', 'analog_in', voltage=5), pin('A3', 'analog_in', voltage=5), pin('A4_SDA', 'i2c_sda', voltage=5), pin('A5_SCL', 'i2c_scl', voltage=5), pin('D0_RX', 'uart_rx', voltage=5), pin('D1_TX', 'uart_tx', voltage=5), pin('D2', 'digital_io', voltage=5), pin('D3_PWM', 'pwm_in', voltage=5), pin('D4', 'digital_io', voltage=5), pin('D5_PWM', 'pwm_in', voltage=5), pin('D6_PWM', 'pwm_in', voltage=5), pin('D7', 'digital_io', voltage=5), pin('D8', 'digital_io', voltage=5), pin('D9_PWM', 'pwm_in', voltage=5), pin('D10_CS', 'spi_cs', voltage=5), pin('D11_MOSI', 'spi_mosi', voltage=5), pin('D12_MISO', 'spi_miso', voltage=5), pin('D13_SCK', 'spi_sck', voltage=5)], 'https://docs.arduino.cc/hardware/nano', voltage=5, current=200, iface='board', driver=None, notes='Classic ATmega328P Nano reference; clone USB bridge and pin labels vary. Not 3.3 V tolerant.'),
    'esp8266_node_mcu': part('NodeMCU ESP8266 board', [pin('VIN', 'power_in', voltage=5), pin('3V3', 'power_out', voltage=3.3), pin('GND', 'ground', voltage=0), pin('D0', 'digital_io', voltage=3.3), pin('D1_SCL', 'i2c_scl', voltage=3.3), pin('D2_SDA', 'i2c_sda', voltage=3.3), pin('D3', 'digital_io', voltage=3.3), pin('D4', 'digital_io', voltage=3.3), pin('D5_SCK', 'spi_sck', voltage=3.3), pin('D6_MISO', 'spi_miso', voltage=3.3), pin('D7_MOSI', 'spi_mosi', voltage=3.3), pin('D8_CS', 'spi_cs', voltage=3.3), pin('RX', 'uart_rx', voltage=3.3), pin('TX', 'uart_tx', voltage=3.3), pin('A0', 'analog_in', voltage=1.0)], 'https://docs.espressif.com/projects/esp8266/', voltage=5, current=300, iface='board', driver=None, notes='ADC input range differs across board variants; boot strap pins must be kept at required levels.'),
    'stm32_bluepill': part('STM32F103C8 Blue Pill board', [pin('3V3', 'power_out', voltage=3.3), pin('5V', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('PB6_SCL', 'i2c_scl', voltage=3.3), pin('PB7_SDA', 'i2c_sda', voltage=3.3), pin('PA5_SCK', 'spi_sck', voltage=3.3), pin('PA6_MISO', 'spi_miso', voltage=3.3), pin('PA7_MOSI', 'spi_mosi', voltage=3.3), pin('PA9_TX', 'uart_tx', voltage=3.3), pin('PA10_RX', 'uart_rx', voltage=3.3), pin('PA0_ADC', 'analog_in', voltage=3.3), pin('PB0', 'digital_io', voltage=3.3), pin('PB1', 'digital_io', voltage=3.3)], 'https://www.st.com/en/microcontrollers-microprocessors/stm32f103c8.html', voltage=5, current=300, iface='board', driver=None, notes='Clone MCU authenticity and bootloader vary; verify board pinout, clock and ADC range.'),
    'logic_analyzer': part('8-channel logic analyzer (test tool)', [pin('GND', 'ground', voltage=0), pin('CH0', 'digital_in', voltage=3.3), pin('CH1', 'digital_in', voltage=3.3), pin('CH2', 'digital_in', voltage=3.3), pin('CH3', 'digital_in', voltage=3.3), pin('CH4', 'digital_in', voltage=3.3), pin('CH5', 'digital_in', voltage=3.3), pin('CH6', 'digital_in', voltage=3.3), pin('CH7', 'digital_in', voltage=3.3)], 'https://sigrok.org/wiki/Supported_hardware', voltage=3.3, current=0, iface='test', driver=None, notes='Measurement accessory, not a circuit load; confirm maximum input voltage and sample rate.'),
    'multimeter': part('Digital multimeter (test tool)', [pin('COM', 'test'), pin('VΩ', 'test'), pin('A', 'test')], 'https://www.fluke.com/', voltage=None, current=0, iface='test', driver=None, notes='Tool representation only; use correct jack/range, never measure current across a supply in voltage mode.'),
    'solderless_jumper_m2m': part('Male-to-male jumper wire set', [pin('END1', 'passive'), pin('END2', 'passive')], 'https://learn.sparkfun.com/tutorials/how-to-use-a-breadboard/all', voltage=None, current=0, iface='passive', driver=None, notes='Verify wire length, connector fit and current suitability.'),
    'screw_terminal_3': part('3-position screw terminal block', [pin('1', 'passive'), pin('2', 'passive'), pin('3', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Match pitch, current rating, wire gauge and insulation spacing.'),
    'proto_pcb': part('Perforated prototyping PCB', [pin('PAD1', 'passive'), pin('PAD2', 'passive'), pin('PAD3', 'passive'), pin('PAD4', 'passive')], 'https://learn.sparkfun.com/tutorials/how-to-use-a-breadboard/all', voltage=None, current=0, iface='passive', driver=None, notes='Generic prototyping substrate; pads are not internally connected unless the board layout says so.'),
    'battery_9v': part('9 V battery with clip', [pin('+', 'power_out', voltage=9), pin('-', 'ground', voltage=0)], 'https://www.energizer.com/', voltage=9, current=100, iface='power', driver=None, notes='Low current capability; not suitable for high-current motors/servos. Check regulator input and runtime.'),
    'battery_lipo_1s': part('1S LiPo battery pack', [pin('+', 'power_out', voltage=3.7), pin('-', 'ground', voltage=0)], 'https://www.analog.com/', voltage=3.7, current=500, iface='power', driver=None, notes='Use matched charger/protection, avoid puncture/shorting and confirm pack discharge rating.'),
    'solar_panel_6v': part('6 V small solar panel', [pin('+', 'power_out', voltage=6), pin('-', 'ground', voltage=0)], 'https://www.analog.com/', voltage=6, current=200, iface='power', driver=None, notes='Output varies with illumination; use a suitable charger/regulator and never connect directly to a battery without charge control.'),
    'ldr_module': part('LDR light sensor module', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=3.3), pin('DO', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=3.3, current=10, iface='analog', driver=None, notes='Module comparator threshold is adjustable; analog range and output logic vary.'),
    'mq135': part('MQ-135 air quality sensor module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=5), pin('DO', 'digital_out', voltage=5)], 'https://www.winsen-sensor.com/', voltage=5, current=180, iface='analog', driver=None, notes='Heater consumes substantial current; AO/DO may be 5 V and need level conditioning; not calibrated ppm or safety monitor.'),
    'mq7': part('MQ-7 carbon monoxide sensor module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=5), pin('DO', 'digital_out', voltage=5)], 'https://www.winsen-sensor.com/', voltage=5, current=180, iface='analog', driver=None, notes='Requires specified heater cycle and calibration; not for life-safety use. 5 V output must be level-shifted.'),
    'turbidity_sensor': part('Turbidity sensor module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=5), pin('DO', 'digital_out', voltage=5)], 'https://docs.arduino.cc/', voltage=5, current=40, iface='analog', driver=None, notes='Output voltage can exceed 3.3 V; condition signal and calibrate against samples. Not potable-water certification.'),
    'ph_sensor': part('pH probe interface module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('PO', 'analog_out', voltage=3.3), pin('DO', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=5, current=10, iface='analog', driver=None, notes='Requires calibration buffers, temperature compensation and high-impedance interface; module versions vary.'),
    'ec_sensor': part('Electrical conductivity sensor interface', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=5, current=20, iface='analog', driver=None, notes='Requires probe-specific calibration and temperature compensation; prevent continuous DC probe polarization.'),
    'soil_cap_analog': part('Capacitive soil moisture sensor generic', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('AO', 'analog_out', voltage=3.3)], 'https://wiki.dfrobot.com/Capacitive_Soil_Moisture_Sensor_SKU_SEN0193', voltage=3.3, current=5, iface='analog', driver=None, notes='Calibrate in the actual soil; analog output scale varies by module and soil conditions.'),
    'waterproof_ultrasonic': part('Waterproof ultrasonic distance sensor', [pin('VCC', 'power_in', voltage=5), pin('TRIG', 'digital_in', voltage=3.3), pin('ECHO', 'digital_out', voltage=5), pin('GND', 'ground', voltage=0)], 'https://docs.arduino.cc/', voltage=5, current=30, iface='digital', driver=None, notes='Level shift ECHO to 3.3 V GPIO; verify exact model timing and connector pinout.'),
    'pir_am312': part('AM312 mini PIR sensor', [pin('VCC', 'power_in', voltage=3.3), pin('OUT', 'digital_out', voltage=3.3), pin('GND', 'ground', voltage=0)], 'https://docs.arduino.cc/', voltage=3.3, current=1, iface='digital', driver=None, notes='Detection distance and hold time vary; avoid treating it as a security-grade detector.'),
    'rotary_pot': part('Panel-mount rotary potentiometer', [pin('END1', 'passive'), pin('WIPER', 'analog_out', voltage=3.3), pin('END2', 'passive')], 'https://docs.arduino.cc/', voltage=3.3, current=0, iface='analog', driver=None, notes='Use as a divider between board-safe rails; verify pin order from datasheet.'),
    'micro_switch': part('Limit microswitch', [pin('COM', 'passive'), pin('NO', 'passive'), pin('NC', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='discrete', driver=None, notes='Contact current/voltage ratings and mechanical travel vary; use pull-up/down and debounce.'),
    'rgb_led': part('RGB LED common-anode/cathode', [pin('R', 'led_anode'), pin('G', 'led_anode'), pin('B', 'led_anode'), pin('COMMON', 'passive')], 'https://docs.arduino.cc/built-in-examples/basics/Blink', voltage=None, current=20, iface='discrete', driver=None, notes='Use one current-limiting resistor per color channel; verify common-anode vs common-cathode.'),
    'transistor_driver': part('Transistor driver stage (generic)', [pin('IN', 'digital_in', voltage=3.3), pin('VCC', 'power_in'), pin('GND', 'ground', voltage=0), pin('OUT', 'load_out')], 'https://learn.sparkfun.com/tutorials/transistors/all', voltage=None, current=500, iface='digital', driver=None, notes='Generic placeholder for planning only; choose transistor, resistor and protection from the load current and voltage.'),
    'dc_dc_regulator': part('Linear voltage regulator module', [pin('VIN', 'power_in'), pin('GND', 'ground', voltage=0), pin('VOUT', 'power_out')], 'https://www.ti.com/power-management/linear-regulators/overview.html', voltage=12, current=500, iface='power', driver=None, notes='Verify dropout, dissipation, thermal conditions and capacitor requirements before use.'),
    'power_switch': part('SPST power switch', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='power', driver=None, notes='Choose DC voltage/current rating and polarity-safe enclosure; switch only within rated limits.'),
    'ferrite_bead': part('Ferrite bead', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.murata.com/', voltage=None, current=0, iface='passive', driver=None, notes='Select impedance-vs-frequency and current rating for the actual EMI/supply problem.'),
    'crystal_16mhz': part('16 MHz crystal resonator', [pin('1', 'passive'), pin('2', 'passive')], 'https://www.digikey.com/', voltage=None, current=0, iface='passive', driver=None, notes='Requires load capacitors and correct oscillator circuit; MCU board crystals are usually already installed.'),
    'cr2032_holder': part('CR2032 coin-cell holder', [pin('+', 'power_out', voltage=3.0), pin('-', 'ground', voltage=0)], 'https://www.energizer.com/', voltage=3.0, current=0, iface='power', driver=None, notes='Use only where the circuit supports coin-cell chemistry; never charge a primary CR2032.'),
    'buzzer_module_5v': part('5 V active buzzer module', [pin('VCC', 'power_in', voltage=5), pin('GND', 'ground', voltage=0), pin('SIG', 'digital_in', voltage=3.3)], 'https://docs.arduino.cc/', voltage=5, current=20, iface='digital', driver=None, notes='Verify input current and active-low/active-high trigger. Bare buzzers may need a transistor.'),
    'solenoid_driver': part('Solenoid driver MOSFET stage', [pin('CTRL', 'digital_in', voltage=3.3), pin('V+', 'power_in'), pin('GND', 'ground', voltage=0), pin('LOAD+', 'load_out'), pin('LOAD-', 'load_out')], 'https://learn.sparkfun.com/tutorials/transistors/all', voltage=12, current=1000, iface='power', driver=None, notes='Generic stage: select MOSFET, gate resistor, pulldown, flyback diode and supply based on actual coil.'),
    'fan_driver': part('Fan MOSFET driver stage', [pin('CTRL', 'digital_in', voltage=3.3), pin('V+', 'power_in'), pin('GND', 'ground', voltage=0), pin('FAN+', 'load_out'), pin('FAN-', 'load_out')], 'https://learn.sparkfun.com/tutorials/transistors/all', voltage=12, current=1000, iface='power', driver=None, notes='Generic planning stage; confirm fan current, PWM requirements, inductive transient and MOSFET thermal rating.'),
    'sensor_breakout_generic': part('Generic 3.3 V sensor breakout', [pin('VCC', 'power_in', voltage=3.3), pin('GND', 'ground', voltage=0), pin('SIG', 'analog_out', voltage=3.3), pin('INT', 'digital_out', voltage=3.3)], 'https://docs.arduino.cc/', voltage=3.3, current=10, iface='generic', driver=None, notes='Planning-only generic breakout; replace with exact model before generating verified wiring or firmware.'),
})
RESISTANCE = {'r100':100, 'r220':220, 'r4k7':4700, 'r10k':10000, 'r15k':15000}


def catalog(conn=None):
    out = copy.deepcopy(CATALOG)
    # Limit initial board support to exact, reviewed ESP32 variants. Other legacy
    # library boards remain available in the original library/tool workflows.
    for key in ('esp32','esp32s3'):
        b = hardware.BOARDS[key]
        allpins = set(b['digital_pool']+b['analog_pool']+b['pwm_pool']+list(b['i2c'].values())+list(b['spi'].values())+list(b['uart'].values()))
        out['board:'+key] = part(b['name'],
            [pin(x, 'gpio', voltage=3.3, required=False) for x in sorted(allpins,key=int)] +
            [pin('VIN','power_in',voltage=5),pin('3V3','power_out',voltage=3.3,required=False),pin('GND','ground',voltage=0)],
            b['docs'], voltage=5, current=500, notes=b['voltage_note'],iface='board')
    if conn:
        for r in conn.execute('SELECT model,definition_json FROM component_definitions'):
            out[r['model']] = json.loads(r['definition_json'])
    return out


def check(graph, conn=None):
    if not isinstance(graph,dict) or graph.get('schema') != SCHEMA:
        raise ApiError(400, 'Expected schema nexus.circuit/1.', 'invalid_circuit')
    nodes, edges = graph.get('components'),graph.get('connections')
    if not isinstance(nodes,list) or not isinstance(edges,list) or not 1 <= len(nodes) <= 80 or len(edges)>300:
        raise ApiError(400, 'Circuit must have 1–80 components and at most 300 connections.', 'invalid_circuit')
    cat, ids, edgeids = catalog(conn),set(),set()
    for n in nodes:
        if not isinstance(n,dict) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}',str(n.get('id',''))):
            raise ApiError(400, 'Each component needs a stable alphanumeric ID.', 'invalid_circuit')
        if n['id'] in ids or n.get('model') not in cat:
            raise ApiError(400, 'Duplicate ID or unsupported component model: '+str(n.get('model')), 'unsupported_component')
        ids.add(n['id'])
        if not isinstance(n.get('position'),dict): n['position']={'x':200,'y':200}
        for k in ('x','y'):
            v=n['position'].get(k,0)
            if not isinstance(v,(int,float)) or not -5000<=v<=5000:
                raise ApiError(400,'Component position is invalid.','invalid_circuit')
    byid={n['id']:n for n in nodes}
    for e in edges:
        if not isinstance(e,dict) or not isinstance(e.get('id'),str) or e['id'] in edgeids:
            raise ApiError(400,'Each connection requires a unique ID.','invalid_circuit')
        edgeids.add(e['id'])
        for end in ('from','to'):
            ep=e.get(end,{})
            if not isinstance(ep,dict) or ep.get('component') not in byid or ep.get('pin') not in [p['id'] for p in cat[byid[ep['component']]['model']]['pins']]:
                raise ApiError(400,'Connection references an unknown component/pin.','invalid_pin')
        if e['from']==e['to']: raise ApiError(400,'A connection cannot join a pin to itself.','invalid_circuit')
    if sum(n['model'].startswith('board:') for n in nodes)!=1:
        raise ApiError(400,'Exactly one supported controller board is required.','invalid_circuit')
    board=next(n for n in nodes if n['model'].startswith('board:'))
    cfg=graph.get('board_config',{})
    if not isinstance(cfg,dict) or cfg.get('board',board['model'][6:]) != board['model'][6:]:
        raise ApiError(400,'Board configuration differs from the actual controller component.','board_mismatch')
    if cfg.get('comms','serial')!='serial':
        raise ApiError(422,'Automatic Studio driver transport currently supports serial only. Add and review network code in Code Engineer; do not assume a configured protocol was implemented.','unsupported_transport')
    return graph


def electrical_hash(g):
    data={'components':sorted([(n['id'],n['model']) for n in g['components']]),
          'connections':sorted([tuple(sorted([(e['from']['component'],e['from']['pin']),(e['to']['component'],e['to']['pin'])])) for e in g['connections']])}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()[:16]


def nets(g, conn=None):
    cat = catalog(conn); parent={}
    def find(x):
        parent.setdefault(x,x)
        if parent[x]!=x: parent[x]=find(parent[x])
        return parent[x]
    for n in g['components']:
        for p in cat[n['model']]['pins']: find((n['id'],p['id']))
    for e in g['connections']:
        a,b = [(e[k]['component'],e[k]['pin']) for k in ('from','to')]
        parent[find(a)]=find(b)
    groups=defaultdict(set)
    for x in parent: groups[find(x)].add(x)
    lookup={x:group for group in groups.values() for x in group}
    return lookup,list(groups.values())


def wiring(g,conn=None):
    cat=catalog(conn);byid={n['id']:n for n in g['components']}
    return [{'id':e['id'], 'from': e['from']['component']+'.'+e['from']['pin'],
             'to':e['to']['component']+'.'+e['to']['pin'],
             'signal': next(p['type'] for p in cat[byid[e['from']['component']]['model']]['pins'] if p['id']==e['from']['pin'])}
            for e in g['connections']]


def board_mappings(g,conn=None):
    cat=catalog(conn);lookup,_=nets(g,conn);board=next(n for n in g['components'] if n['model'].startswith('board:'))
    def resolve(endpoint,visited=None):
        visited=visited or set()
        if endpoint in visited: return None
        visited.add(endpoint)
        for cid,p in lookup[endpoint]:
            if cid==board['id'] and p.isdigit(): return p
        for cid,p in lookup[endpoint]:
            node=next(n for n in g['components'] if n['id']==cid)
            if node['model'] in RESISTANCE:
                other=(cid,'2' if p=='1' else '1')
                result=resolve(other,visited)
                if result:return result
        return None
    out={}
    for n in g['components']:
        if n['id']==board['id']:continue
        for p in cat[n['model']]['pins']:
            if p['type'] in ('analog_out','digital_in','digital_io','gate','led_anode','i2c_sda','i2c_scl'):
                v=resolve((n['id'],p['id']))
                if v:out[n['id']+'_'+p['id']]=v
    return out


def build_guide(g, conn=None):
    """Create a deterministic, graph-derived physical assembly guide.

    This reports only connections actually present in the saved graph. It does
    not infer missing wires or certify a design as electrically safe.
    """
    check(g, conn)
    cat = catalog(conn)
    byid = {n['id']: n for n in g['components']}
    result = validate(g, conn)
    steps = []
    # Explicitly require power-off assembly before any terminal-by-terminal work.
    steps.append({
        'number': 1, 'title': 'Power off and identify parts',
        'instruction': 'Disconnect USB and every external supply. Match each physical board/module to its exact catalog model and confirm terminal labels against its manufacturer documentation.',
        'kind': 'safety'
    })
    for i, edge in enumerate(wiring(g, conn), start=2):
        steps.append({
            'number': i, 'title': f"Connect {edge['from']} to {edge['to']}",
            'instruction': f"Connect {edge['from']} directly to {edge['to']} as represented in the current circuit graph. Signal/pin role at source: {edge['signal']}. Do not infer physical header position from the visual layout; use the printed pin label and board pinout.",
            'kind': 'connection'
        })
    next_number = len(steps) + 1
    steps.append({
        'number': next_number, 'title': 'Inspect before applying power',
        'instruction': 'Check polarity, continuity, unintended shorts, common-ground requirements, supply voltage and current capacity. Keep loads disconnected until driver and protection wiring is confirmed.',
        'kind': 'checkpoint'
    })
    unconnected = []
    lookup, _ = nets(g, conn)
    for node in g['components']:
        for terminal in cat[node['model']]['pins']:
            if terminal['required'] and len(lookup[(node['id'], terminal['id'])]) < 2:
                unconnected.append({'component': node['id'], 'model': node['model'], 'pin': terminal['id'], 'role': terminal['type']})
    component_notes = [
        {'component': n['id'], 'model': n['model'], 'name': cat[n['model']]['name'],
         'notes': cat[n['model']].get('notes', ''), 'reference': cat[n['model']].get('reference', '')}
        for n in g['components'] if not n['model'].startswith('board:')
    ]
    bom_map = {}
    for n in g['components']:
        model = n['model']
        if model.startswith('board:'):
            continue
        item = bom_map.setdefault(model, {'model': model, 'name': cat[model]['name'], 'quantity': 0,
                                          'estimated_current_ma_each': cat[model].get('current_ma'),
                                          'reference': cat[model].get('reference', ''),
                                          'notes': cat[model].get('notes', '')})
        item['quantity'] += 1
    bill_of_materials = sorted(bom_map.values(), key=lambda x: x['name'].lower())
    errors = [x for x in result['issues'] if x['severity'] == 'error']
    warnings = [x for x in result['issues'] if x['severity'] in ('warning', 'info')]
    return {
        'title': 'NEXUS step-by-step circuit build guide',
        'schema': SCHEMA,
        'graph_fingerprint': result['fingerprint'],
        'component_count': len(g['components']),
        'connection_count': len(g['connections']),
        'steps': steps,
        'component_notes': component_notes,
        'bill_of_materials': bill_of_materials,
        'unconnected_required_terminals': unconnected,
        'blocking_errors': errors,
        'warnings': warnings,
        'ready_for_power': not errors and not unconnected,
        'status': 'graph_derived_guidance_not_physical_verification',
        'limitations': ['Only connections in the current graph are listed; no missing wire is silently invented.',
                       'Confirm exact breakout revision, datasheet, voltage/current ratings and physical pin labels.',
                       'A successful rule check is not a guarantee of error-free hardware.']
    }


def validate(g,conn=None):
    check(g,conn);cat=catalog(conn);lookup,groups=nets(g,conn);byid={n['id']:n for n in g['components']};findings=[]
    board=next(n for n in g['components'] if n['model'].startswith('board:'));b=hardware.BOARDS[board['model'][6:]]
    meta={(n['id'],p['id']):p for n in g['components'] for p in cat[n['model']]['pins']}
    def issue(severity,code,message,evidence,fix):
        findings.append(dict(severity=severity,code=code,message=message,evidence=evidence,fix=fix))
    for ep,p in meta.items():
        if p['required'] and len(lookup[ep])<2:
            issue('error','MISSING_CONNECTION','Required terminal is not connected.', '.'.join(ep),'Connect this exact terminal; confirm the datasheet pinout.')
    for group in groups:
        if len(group)<2:continue
        labels=', '.join('.'.join(ep) for ep in sorted(group))
        sources=[(ep,meta[ep]['voltage']) for ep in group if meta[ep]['type'] in ('power_out','ground')]
        volts={v for ep,v in sources if v is not None}
        if len(volts)>1:issue('error','RAIL_SHORT','Different supply/ground potentials are shorted.',labels,'Separate the power and ground nets before applying power.')
        gp=[ep[1] for ep in group if ep[0]==board['id'] and ep[1].isdigit()]
        if len(gp)>1:issue('error','GPIO_SHORT','Multiple controller GPIOs are on the same net.',labels,'Assign each independent signal to one GPIO.')
        outputs=[ep for ep in group if meta[ep]['type'] in ('analog_out','digital_out')]
        if outputs and sources:
            issue('error','SIGNAL_RAIL_SHORT','A driven signal is tied directly to a power/ground rail.',labels,'Remove the direct rail connection; use required bias/level-shifting circuitry instead.')
        for ep in group:
            p=meta[ep]
            for source,v in sources:
                if p['type']=='power_in' and p['voltage'] is not None and v>p['voltage']+0.15:
                    issue('error','SUPPLY_VOLTAGE','Supply exceeds the assumed component voltage.',labels,'Use the correct regulated rail; verify absolute maximum ratings.')
            if ep[0]==board['id'] and ep[1].isdigit():
                analogs=[x for x in group if meta[x]['type']=='analog_out']
                outputs=[x for x in group if meta[x]['type'] in ('digital_out','analog_out')]
                if len(outputs)>1:issue('error','OUTPUT_CONFLICT','Two driven outputs share a GPIO net.',labels,'Separate these signal outputs.')
                for x in outputs:
                    if (meta[x].get('voltage') or 0)>b['logic_v']+0.1:
                        issue('error','LOGIC_VOLTAGE','Direct signal can exceed controller logic voltage.',labels,'Use a documented divider/level-shifter and validate its ratio.')
                if analogs and ep[1] not in b['analog_pool']:
                    issue('error','NO_ADC','Analog signal is not on a supported ADC1 pin.',labels,'Select a supported ADC1 GPIO; ADC2 conflicts with Wi-Fi.')
                if ep[1] in b['input_only'] and any(meta[x]['type'] in ('digital_in','gate','led_anode') for x in group):
                    issue('error','INPUT_ONLY','An output is mapped to an input-only GPIO.',labels,'Use an output-capable GPIO.')
                if any(byid[x[0]]['model']=='pump' for x in group):
                    issue('error','GPIO_CURRENT','A pump terminal is connected to a GPIO.',labels,'Use an external supply, MOSFET, gate pulldown and flyback diode.')
    mappings=board_mappings(g,conn)
    for n in g['components']:
        model=n['model'];cid=n['id']
        if model=='gas_mq2':
            ao=lookup[(cid,'AO')]; verified=False
            for rid,rpin in ao:
                if byid[rid]['model'] not in RESISTANCE:continue
                junction=lookup[(rid,'2' if rpin=='1' else '1')]
                for bid,bpin in junction:
                    if bid==rid or byid[bid]['model'] not in RESISTANCE:continue
                    low=lookup[(bid,'2' if bpin=='1' else '1')]
                    if any(meta[x]['type']=='ground' for x in low) and any(x[0]==board['id'] and x[1] in b['analog_pool'] for x in junction):
                        v=5*RESISTANCE[byid[bid]['model']]/(RESISTANCE[byid[rid]['model']]+RESISTANCE[byid[bid]['model']])
                        verified=v<=3.3
                        if not verified:issue('error','DIVIDER_RATIO',f'Divider worst-case input at 5 V is {v:.2f} V.',cid,'Choose a divider below 3.3 V with tolerance margin.')
            if not verified:issue('error','MQ2_DIVIDER','No supported, bounded 5 V to 3.3 V divider path was found.',cid,'Use 10 kΩ series and 15 kΩ to GND; ADC1 at their junction. Verify maximum supply/tolerances.')
            issue('warning','GAS_LIMITATION','Raw gas index is educational, not a certified alarm or ppm measurement.',cid,'Use a certified detector for safety; test only with safe simulated ADC inputs.')
        if model=='mosfet':
            if (board['id'],'GND') not in lookup[(cid,'S')]:
                issue('error','MOSFET_SOURCE','Low-side MOSFET source is not on controller ground.',cid+'.S','Connect source S to the common low-voltage ground; confirm device orientation.')
            gate=lookup[(cid,'G')]
            has_pull=False
            for rid,rpin in gate:
                if byid[rid]['model']=='r10k':
                    other=lookup[(rid,'2' if rpin=='1' else '1')]
                    has_pull|=any(meta[x]['type']=='ground' for x in other)
            if not has_pull:issue('error','GATE_PULLDOWN','MOSFET gate has no supported 10 kΩ pulldown.',cid,'Add gate-to-GND pulldown and ensure OFF at reset.')
        if model=='pump':
            plus,minus=lookup[(cid,'+')],lookup[(cid,'-')]
            protected=any(byid[x[0]]['model']=='diode' and x[1]=='K' and (x[0],'A') in minus for x in plus)
            driven=any(byid[x[0]]['model']=='mosfet' and x[1]=='D' for x in minus)
            if not protected or not driven:issue('error','PUMP_DRIVER','Pump lacks the expected low-side driver / reverse-biased flyback diode.',cid,'Place diode K at pump +, A at pump −; MOSFET D at − and S at GND.')
            issue('warning','STALL_CURRENT','Pump stall/inrush current and MOSFET thermal performance are unverified.',cid,'Measure stall/inrush safely with a current-limited supply; size diode, wiring and fuse.')
        if model=='dht22':
            group=lookup[(cid,'DATA')]
            pull=False
            for rid,rpin in group:
                if byid[rid]['model']=='r4k7' and any(meta[x]['type']=='power_out' and meta[x]['voltage']==3.3 for x in lookup[(rid,'2' if rpin=='1' else '1')]):pull=True
            if not pull:issue('warning','PULLUP','DHT22 pull-up not found in graph.',cid,'Add 4.7 kΩ DATA-to-3V3 or confirm the breakout includes it.')
        if model=='bme280':
            for p,key in [('SDA','SDA'),('SCL','SCL')]:
                if (board['id'],b['i2c'][key]) not in lookup[(cid,p)] and mappings.get(cid+'_'+p):
                    issue('info','CUSTOM_I2C_PIN','Non-default I2C GPIO is used by graph-derived Wire.begin constants.',cid+'.'+p,'Verify this GPIO is output-capable and the breakout pull-ups are appropriate.')
                if mappings.get(cid+'_'+p) in b['input_only']:
                    issue('error','INPUT_ONLY','I2C requires an output-capable open-drain GPIO.',cid+'.'+p,'Choose a supported output-capable bus pin.')
            if mappings.get(cid+'_SDA') and mappings.get(cid+'_SDA')==mappings.get(cid+'_SCL'):
                issue('error','I2C_PIN_CONFLICT','SDA and SCL are assigned to the same GPIO.',cid,'Separate SDA and SCL and regenerate pin configuration.')
            issue('warning','I2C_PULLUPS','Breakout pull-up values/address require confirmation.',cid,'Confirm pull-ups go to 3.3 V and total bus pull-up is appropriate.')
        if model=='led' and not any(byid[x[0]]['model']=='r220' for x in lookup[(cid,'A')]):
            issue('error','LED_RESISTOR','LED has no supported current-limiting resistor.',cid,'Put a 220 Ω series resistor between GPIO and anode.')
    addresses=[n for n in g['components'] if n['model']=='bme280']
    if len(addresses)>1:issue('error','I2C_ADDRESS','Multiple BME280 instances assume the same 0x76 address.','BME280 bus','Use address selection/multiplexer; automatic multi-address driver is not supported yet.')
    issue('warning','UNVERIFIED_HARDWARE','Rule checks do not establish electrical safety, successful simulation or a working physical device.','All components','Confirm exact module pinout, resistor tolerances, power budget, continuity, polarity and bench test before deployment.')
    # Validate mapped roles even when a series/divider resistor lies between
    # the component terminal and the GPIO.
    for n in g['components']:
        if n['model'].startswith('board:'): continue
        for p in cat[n['model']]['pins']:
            assigned=mappings.get(n['id']+'_'+p['id'])
            if not assigned: continue
            if p['type']=='analog_out' and assigned not in b['analog_pool']:
                issue('error','NO_ADC','Resistor-path analog signal is not on a supported ADC1 pin.',n['id']+'.'+p['id'],'Use an ADC1-capable GPIO.')
            if p['type'] in ('gate','digital_in','led_anode') and assigned in b['input_only']:
                issue('error','INPUT_ONLY','Resistor-path output is assigned to an input-only GPIO.',n['id']+'.'+p['id'],'Choose an output-capable GPIO.')
    for n in g['components']:
        compatible=cat[n['model']].get('compatible_boards') or []
        if compatible and board['model'][6:] not in compatible:
            issue('error','INCOMPATIBLE_BOARD','Component definition does not support the selected board family.',n['id'],'Choose a compatible, reviewed board/component definition.')
        for p in cat[n['model']]['pins']:
            if p['type']=='ground' and n['id']!=board['id'] and (board['id'],'GND') not in lookup[(n['id'],p['id'])]:
                issue('error','COMMON_GROUND','Component ground is not on the controller ground net.',n['id']+'.'+p['id'],'Join the intended low-voltage common ground; verify isolation requirements.')
    budget=sum(cat[n['model']].get('current_ma') or 0 for n in g['components'] if n['model']!='supply5')
    supplies=[n for n in g['components'] if n['model']=='supply5']
    if supplies and budget>1000:
        issue('error','SUPPLY_CAPACITY',f'Assumed load budget {budget} mA exceeds the assumed 1 A supply.','Catalog assumptions only','Size a reviewed supply and protection for continuous load plus inrush/stall margin.')
    return {'issues':findings, 'passed':not any(i['severity']=='error' for i in findings),
            'status':'rule_checked_not_physically_tested', 'simulation':'not_run_no_simulator',
            'wiring':wiring(g,conn), 'mappings':mappings,
            'current_budget_ma_assumed':sum(cat[n['model']].get('current_ma') or 0 for n in g['components'] if n['model']!='supply5'),
            'fingerprint':electrical_hash(g)}


def build(board_key,models):
    if board_key not in ('esp32','esp32s3'):
        raise ApiError(400,'Interactive Studio currently supports documented ESP32/ESP32-S3 boards only. Other library boards remain readable.','unsupported_board')
    if any(m not in CATALOG for m in models):
        raise ApiError(400,'Unsupported part; add a reviewed definition instead of inventing a pinout.','unsupported_component')
    g={'schema':SCHEMA,'board_config':{'board':board_key,'comms':'serial'},'components':[], 'connections':[], 'metadata':{'physical_tested':False}}
    def node(model,id,x,y):g['components'].append({'id':id,'model':model,'label':CATALOG.get(model,{}).get('name',model),'position':{'x':x,'y':y}});return id
    def wire(a,ap,b,bp):g['connections'].append({'id':'w'+str(len(g['connections'])+1),'from':{'component':a,'pin':ap},'to':{'component':b,'pin':bp}})
    node('board:'+board_key,'board',400,200);node('supply5','supply',80,70)
    wire('supply','5V','board','VIN');wire('supply','GND','board','GND')
    b=hardware.BOARDS[board_key];apool=iter(b['analog_pool']);dp=iter([p for p in b['digital_pool'] if p not in b['i2c'].values()]);index=0
    for model in dict.fromkeys(models):
        if model=='supply5':continue
        if model not in ('soil_cap','gas_mq2','bme280','oled_ssd1306','dht22','pump','buzzer','led'):
            node(model,model,720,80+index*140);index+=1;continue  # intentional unwired part, validator explains
        cid=node(model,model,720,80+index*160);index+=1
        def ground():wire(cid,'GND','board','GND')
        if model in ('soil_cap','gas_mq2','bme280','oled_ssd1306','dht22','buzzer'):
            wire(cid,'VCC','supply' if model=='gas_mq2' else 'board','5V' if model=='gas_mq2' else '3V3');ground()
        if model=='soil_cap':wire(cid,'AO','board',next(apool))
        if model=='gas_mq2':
            node('r10k','divider_top',720,80+index*160);node('r15k','divider_bottom',980,80+index*160)
            wire(cid,'AO','divider_top','1');wire('divider_top','2','divider_bottom','1');wire('divider_top','2','board',next(apool));wire('divider_bottom','2','board','GND');index+=1
        if model in ('bme280','oled_ssd1306'):
            wire(cid,'SDA','board',b['i2c']['SDA']);wire(cid,'SCL','board',b['i2c']['SCL'])
        if model=='dht22':
            wire(cid,'DATA','board',next(dp));node('r4k7','dht_pullup',980,80+(index-1)*160);wire(cid,'DATA','dht_pullup','1');wire('dht_pullup','2','board','3V3')
        if model=='pump':
            node('mosfet','driver',720,80+index*160);node('r100','gate_series',980,80+index*160);node('r10k','gate_pull',980,220+index*160);node('diode','flyback',980,80+(index-1)*160)
            wire('supply','5V',cid,'+');wire(cid,'-','driver','D');wire('driver','S','board','GND');wire('board',next(dp),'gate_series','1');wire('gate_series','2','driver','G');wire('driver','G','gate_pull','1');wire('gate_pull','2','board','GND');wire(cid,'+','flyback','K');wire(cid,'-','flyback','A');index+=2
        if model=='buzzer':wire(cid,'SIG','board',next(dp))
        if model=='led':
            node('r220','led_series',980,80+(index-1)*160);wire('board',next(dp),'led_series','1');wire('led_series','2',cid,'A');wire(cid,'K','board','GND')
    return check(g)


def constant(key):return 'NX_'+re.sub('[^A-Za-z0-9]','_',key).upper()


def managed(g,conn=None):
    mappings=board_mappings(g,conn)
    return '// <NEXUS:PINS>\n// Derived from exact-pin graph; do not edit this region.\n'+'\n'.join('#define '+constant(k)+' '+v for k,v in sorted(mappings.items()))+'\n// </NEXUS:PINS>'


def firmware(g,conn=None):
    check(g,conn);cat=catalog(conn);mapping=board_mappings(g,conn);lines=['// NEXUS generated firmware. Static checks only; NOT compiled or hardware-tested.',
       '#include <Arduino.h>', '#include <Wire.h>', '#include <math.h>'];setup=['Serial.begin(115200);'];loop=[];warnings=[];models={n['model'] for n in g['components']};globals=[];libs=[]
    for n in g['components']:
        cid=n['id'];model=n['model'];safe=re.sub('[^a-zA-Z0-9_]','_',cid)
        def get(p):return constant(cid+'_'+p) if cid+'_'+p in mapping else None
        if model in ('soil_cap','gas_mq2'):
            p=get('AO')
            if not p:warnings.append(cid+': analog signal is unassigned; driver omitted.');continue
            setup.append(f'pinMode({p}, INPUT);')
            loop += [f'const int {safe}_raw = analogRead({p});',f'Serial.printf("{safe}_raw=%d\\n", {safe}_raw);']
            if model=='soil_cap':
                globals += [f'// Calibrate dry/wet raw counts for {cid}; these are PLACEHOLDERS.',f'const float {safe}_dry=3071.0f, {safe}_wet=1433.0f;']
                loop += [f'const float {safe}_pct = constrain(100.0f * ({safe}_dry - {safe}_raw) / ({safe}_dry - {safe}_wet),0.0f,100.0f);']
            else:loop += ['// Gas raw index only. Heater warm-up/calibration required; never a certified gas alarm.']
        elif model=='bme280':
            sda,scl=get('SDA'),get('SCL')
            if not sda or not scl:
                warnings.append(cid+': I2C bus unassigned; driver omitted.');continue
            lines+=['#include <Adafruit_BME280.h>'];libs+=['Adafruit BME280 Library + Adafruit Unified Sensor'];globals += [f'Adafruit_BME280 {safe};',f'bool {safe}_ready=false;'];setup += [f'Wire.begin({sda}, {scl}); {safe}_ready={safe}.begin(0x76);',f'if(!{safe}_ready) Serial.println("BME280 not found; verify wiring/address");'];loop += [f'if({safe}_ready) Serial.printf("temperature_c=%.2f humidity_pct=%.2f\\n",{safe}.readTemperature(),{safe}.readHumidity());']
        elif model=='oled_ssd1306':
            sda,scl=get('SDA'),get('SCL')
            if not sda or not scl:
                warnings.append(cid+': I2C bus unassigned; OLED driver omitted.');continue
            lines+=['#include <Adafruit_GFX.h>','#include <Adafruit_SSD1306.h>']
            libs+=['Adafruit GFX Library','Adafruit SSD1306']
            globals += [f'Adafruit_SSD1306 {safe}(128, 64, &Wire, -1);',f'bool {safe}_ready=false;']
            setup += [f'Wire.begin({sda}, {scl}); {safe}_ready={safe}.begin(SSD1306_SWITCHCAPVCC, 0x3C);',f'if(!{safe}_ready) Serial.println("OLED not found; check I2C address 0x3C/0x3D");',f'if({safe}_ready) {{ {safe}.clearDisplay(); {safe}.setTextSize(1); {safe}.setTextColor(SSD1306_WHITE); {safe}.setCursor(0,0); {safe}.println("NEXUS IoT"); {safe}.println("Boot complete"); {safe}.display(); }}']
            loop += [f'if({safe}_ready) {{ {safe}.fillRect(0, 16, 128, 48, SSD1306_BLACK); {safe}.setCursor(0,16); {safe}.println("System running"); {safe}.display(); }}']
        elif model=='dht22':
            p=get('DATA')
            if not p:warnings.append(cid+': DATA unassigned.');continue
            lines+=['#include <DHT.h>'];libs+=['DHT sensor library by Adafruit + Unified Sensor'];globals += [f'DHT {safe}({p}, DHT22);'];setup += [f'{safe}.begin();'];loop += [f'float {safe}_t={safe}.readTemperature();',f'if(isnan({safe}_t)) Serial.println("DHT read failed"); else Serial.println({safe}_t);']
        elif model in ('mosfet','buzzer','led'):
            p=get({'mosfet':'G','buzzer':'SIG','led':'A'}[model])
            if not p:warnings.append(cid+': output unassigned.');continue
            setup += [f'pinMode({p}, OUTPUT); digitalWrite({p},LOW); // fail safe OFF at boot']
        elif not model.startswith('board:') and model not in ('supply5','pump','r220','r100','r4k7','r10k','r15k','diode'):
            warnings.append(cid+': no executable driver template. Add a reviewed driver manually; pinout is not invented.')
    soil=next((n for n in g['components'] if n['model']=='soil_cap'),None);switch=next((n for n in g['components'] if n['model']=='mosfet'),None)
    if soil and switch and soil['id']+'_AO' in mapping and switch['id']+'_G' in mapping:
        s=re.sub('[^a-zA-Z0-9_]','_',soil['id']);p=constant(switch['id']+'_G')
        globals += ['bool pump_on=false; unsigned long pump_started=0, pump_stopped=0; bool pump_has_run=false;']
        loop += [f'const bool sensor_valid={s}_raw > 50 && {s}_raw < 4045;', f'if(!sensor_valid || (pump_on && millis()-pump_started>=10000) || {s}_pct>55.0f) {{ if(pump_on) pump_stopped=millis(); pump_on=false; }}', f'else if(!pump_on && {s}_pct<30.0f && (!pump_has_run || millis()-pump_stopped>=60000)) {{ pump_on=true; pump_has_run=true; pump_started=millis(); }}',f'digitalWrite({p},pump_on ? HIGH:LOW); // bench-confirm driver active HIGH']
        warnings.append('Irrigation prototype: nominal 10 s run timer plus sampling latency and 60 s cooldown are not an independent interlock or daily water budget. Confirm calibration; add dry-run/level protection before unattended use.')
    gas=next((n for n in g['components'] if n['model']=='gas_mq2'),None);buzz=next((n for n in g['components'] if n['model']=='buzzer'),None)
    if gas and buzz and gas['id']+'_AO' in mapping and buzz['id']+'_SIG' in mapping:
        s=re.sub('[^a-zA-Z0-9_]','_',gas['id']);loop += [f'// 2200 raw ADC threshold is an educational PLACEHOLDER, NOT calibrated ppm.',f'digitalWrite({constant(buzz["id"]+"_SIG")}, {s}_raw > 2200 ? HIGH : LOW);']
    lines += [managed(g,conn), *globals, 'void setup() {', *['  '+l for l in setup],'}', 'void loop() {', *['  '+l for l in loop], '  delay(2500);','}']
    code='\n'.join(dict.fromkeys(lines[:3]))+'\n'+'\n'.join(lines[3:])+'\n'
    return {'language':'cpp','filename':'firmware.ino','code':code,'libraries':list(dict.fromkeys(libs)),
            'graph_hash':electrical_hash(g),'topology':[ [n['id'],n['model']] for n in g['components']],
            'status':'incomplete' if any('omitted' in w or 'unassigned' in w or 'no executable' in w for w in warnings) else 'generated_not_compiled',
            'warnings':warnings, 'user_edited':False,
            'instructions':['Arduino IDE: install Espressif ESP32 core 3.x; select the exact board.', 'Install listed libraries; compile locally (no compiler installed here).', 'Replace calibration placeholders; compare every define with the wiring table.', 'Power off, continuity-check, current-limit the supply, then upload and observe serial at 115200 baud.']}


def sync(old_fw,g,conn=None):
    """Only replace marked pin region, preserving every unrelated user edit."""
    fw=copy.deepcopy(old_fw);newblock=managed(g,conn);pattern=r'// <NEXUS:PINS>.*?// </NEXUS:PINS>'
    topology=sorted([[n['id'],n['model']] for n in g['components']])
    oldtop=sorted(fw.get('topology',[]));changed=fw.get('graph_hash')!=electrical_hash(g)
    if not changed:return fw, {'changed':False,'requires_regeneration':False}
    if not re.search(pattern,fw.get('code',''),re.S):
        fw['mismatch']=True
        return fw,{'changed':True,'requires_regeneration':True,'reason':'Managed pin markers missing. User code preserved; review and merge manually.'}
    fw['code']=re.sub(pattern,lambda _:newblock,fw['code'],count=1,flags=re.S)
    fw['graph_hash']=electrical_hash(g);fw['mismatch']=oldtop!=topology;fw['topology']=topology
    return fw,{'changed':True,'requires_regeneration':oldtop!=topology,'reason':'Pin constants synchronized. '+('Components changed: review/rebuild drivers; unrelated user code preserved.' if oldtop!=topology else 'Unrelated code preserved.')}


def svg(g,conn=None):
    cat=catalog(conn);byid={n['id']:n for n in g['components']};coords={};out=[]
    for n in g['components']:
        ps=cat[n['model']]['pins'];x,y=n['position']['x'],n['position']['y']
        for i,p in enumerate(ps):coords[(n['id'],p['id'])]=(x+(210 if i%2 else 0),y+48+(i//2)*22)
    maxx=max(n['position']['x']+260 for n in g['components']);maxy=max(n['position']['y']+max(100,48+len(cat[n['model']]['pins'])//2*22)+50 for n in g['components'])
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-30 -30 {maxx+60} {maxy+60}" role="img" aria-label="Exact-pin connection diagram">')
    out.append('<style>text{font:12px monospace;fill:#d7e3f3}.wire{fill:none;stroke:#4e8295;stroke-width:2}.node{fill:#142235;stroke:#557087} .pin{fill:#63c6b6}</style><rect x="-30" y="-30" width="100%" height="100%" fill="#0b1420"/>')
    for e in g['connections']:
        a=coords[(e['from']['component'],e['from']['pin'])];b=coords[(e['to']['component'],e['to']['pin'])];out.append(f'<path class="wire" d="M{a[0]} {a[1]} H{(a[0]+b[0])/2} V{b[1]} H{b[0]}"/>')
    for n in g['components']:
        x,y=n['position']['x'],n['position']['y'];ps=cat[n['model']]['pins'];h=max(90,60+((len(ps)+1)//2)*22)
        out.append(f'<g data-node="{html.escape(n["id"],quote=True)}"><rect class="node" x="{x}" y="{y}" width="210" height="{h}" rx="8"/><text x="{x+10}" y="{y+20}">{html.escape(n["id"])}</text><text x="{x+10}" y="{y+36}" style="font-size:10px;fill:#8fa7c4">{html.escape(n["model"])}</text>')
        for i,p in enumerate(ps):
            px,py=coords[(n['id'],p['id'])];anchor='end' if i%2 else 'start';tx=px-9 if i%2 else px+9
            out.append(f'<circle class="pin" cx="{px}" cy="{py}" r="4"/><text x="{tx}" y="{py+4}" text-anchor="{anchor}">{html.escape(p["id"])}</text>')
        out.append('</g>')
    out.append('</svg>');return ''.join(out)
