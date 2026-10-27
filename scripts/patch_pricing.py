import os

# 1. Update config.py
config_path = r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\nexus\config.py"
with open(config_path, "rb") as f:
    cfg = f.read()

cfg = cfg.replace(b'"amount": 19.0,', b'"amount": 3.0,')

with open(config_path, "wb") as f:
    f.write(cfg)

# 2. Update billing.py
billing_path = r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\nexus\billing.py"
with open(billing_path, "rb") as f:
    bil = f.read()

bil = bil.replace(b'pay.get("amount", 19.0)', b'pay.get("amount", 3.0)')

with open(billing_path, "wb") as f:
    f.write(bil)

print("Updated default subscription pricing to $3.00 / month USD!")
