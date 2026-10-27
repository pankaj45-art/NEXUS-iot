import os

path = r"C:\Users\Pankaj R\.gemini\antigravity\scratch\nexus-v2\nexus-iot\web\app.js"
with open(path, "r", encoding="utf-8") as f:
    c = f.read()

target = """    } catch (e) {
      $('#auth-alert').innerHTML = `<div class="notice danger mb">${esc(e.message)}</div>`;
      status('NEXUS · error: ' + e.message);
      $('#a-submit').disabled = false;
    }"""

replacement = """    } catch (e) {
      let alertContent = `<div class="notice danger mb">${esc(e.message)}`;
      if (e.message && e.message.toLowerCase().includes('already exists')) {
        alertContent += `<div class="mt-s tiny"><a href="#/login" style="color:#38bdf8;font-weight:bold;text-decoration:underline;">Click here to Sign In with this email →</a></div>`;
      }
      alertContent += `</div>`;
      $('#auth-alert').innerHTML = alertContent;
      status('NEXUS · error: ' + e.message);
      $('#a-submit').disabled = false;
    }"""

if target in c:
    c = c.replace(target, replacement)
    with open(path, "w", encoding="utf-8") as f:
        f.write(c)
    print("Added smart Sign In redirection hint on existing account error!")
else:
    print("Target not found in web/app.js")
