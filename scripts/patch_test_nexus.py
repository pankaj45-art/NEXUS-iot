import os

path = r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\tests\test_nexus.py"
with open(path, "rb") as f:
    content = f.read()

content = content.replace(b".read_text()", b'.read_text(encoding="utf-8")')

with open(path, "wb") as f:
    f.write(content)

print("Updated read_text() with encoding=utf-8 successfully!")
