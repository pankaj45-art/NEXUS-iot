import sys
sys.path.insert(0, '.')
from nexus import db, entitlements
from nexus.services import designs, circuits, code_ai

c = db.connect()
u = c.execute("SELECT * FROM users WHERE email='pro@nexus.local'").fetchone()
ent = entitlements.resolve(c, u)
g = circuits.build('esp32', ['soil_cap', 'bme280'])
p = designs.create(c, ent, 'Smart Garden Test', {'problem': 'Automate plant watering'}, g)

# Test 1: Half Breadboard
res1 = code_ai.propose(c, ent, p['id'], 'Generate complete firmware for Half-Size 400-point breadboard with EMA filter and MQTT')
print("=== Test 1: Half Breadboard ===")
print("Summary:", res1['summary'])
print("Libraries:", res1['libraries'])
print("Has Breadboard Guide:", 'BREADBOARD WIRING & PHYSICAL ASSEMBLY GUIDE' in res1['code'])
print("Has 400 Tie-Points:", '400 Tie-Points' in res1['code'])
print("Has EMA Filter:", 'emaFilter' in res1['code'])
print("Has Setup & Loop:", 'void setup()' in res1['code'] and 'void loop()' in res1['code'])

# Test 2: Mini Breadboard
res2 = code_ai.propose(c, ent, p['id'], 'Generate complete code for mini 170 breadboard with PID controller')
print("\n=== Test 2: Mini Breadboard ===")
print("Summary:", res2['summary'])
print("Has 170 Tie-Points:", '170 Tie-Points' in res2['code'])
print("Has PID Controller:", 'computePID' in res2['code'])

# Test 3: Full 830 Breadboard
res3 = code_ai.propose(c, ent, p['id'], 'Generate complete code for 830 tie-point breadboard with deep sleep and OLED')
print("\n=== Test 3: Full 830 Breadboard ===")
print("Summary:", res3['summary'])
print("Has 830 Tie-Points:", '830 Tie-Points' in res3['code'])
print("Has Deep Sleep:", 'esp_deep_sleep_start' in res3['code'])
print("Has OLED:", 'Adafruit_SSD1306' in res3['code'])

# Print a preview of the generated breadboard guide
lines = res1['code'].splitlines()
print("\n=== Breadboard Header Preview (first 25 lines) ===")
print("\n".join(lines[:25]))
