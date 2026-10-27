import os

path = r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\web\app.js"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

old_shell_main = """      </header>
      <main class="content" id="view"><div class="boot"><div class="spinner"></div></div></main>
    </div></div>"""

new_shell_main = """      </header>
      ${!ent?.is_pro ? `<div class="admob-banner" style="background:rgba(15,23,42,0.95);border-bottom:1px solid rgba(56,189,248,0.2);padding:7px 18px;display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#94a3b8;backdrop-filter:blur(6px);z-index:20;">
        <div style="display:flex;align-items:center;gap:8px;">
          <span style="background:#f59e0b;color:#0b0f19;font-weight:800;font-size:9.5px;padding:1px 6px;border-radius:3px;letter-spacing:0.04em;">AD</span>
          <span>Google AdMob Partner Banner · Free Tier Active · Upgrade to Pro ($3/mo) for 100% Ad-Free Engineering</span>
        </div>
        <a href="#/upgrade" style="color:#38bdf8;font-weight:700;text-decoration:none;display:flex;align-items:center;gap:4px;">⚡ Upgrade to Pro ($3/mo)</a>
      </div>` : ''}
      <main class="content" id="view"><div class="boot"><div class="spinner"></div></div></main>
    </div></div>"""

if old_shell_main in c:
    c = c.replace(old_shell_main, new_shell_main)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Added AdMob banner slot for Free Tier in web/app.js!")
else:
    print("Target not found in web/app.js")
