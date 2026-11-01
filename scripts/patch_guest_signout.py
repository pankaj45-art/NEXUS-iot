"""Patch app.js to update shell() sidebar for guest users."""
import sys
from pathlib import Path

APP = Path(__file__).parent.parent / 'web' / 'app.js'
content = APP.read_text(encoding='utf-8')

OLD = (
    "        <button class=\"btn ghost sm mt-s\" style=\"width:100%\" id=\"logout\">Sign out</button>\n"
)

NEW = (
    "        ${state.me?.is_guest ? `<a href=\"#/login\" class=\"btn primary sm mt-s\" style=\"width:100%\">🔐 Sign In / Register</a>` : `<button class=\"btn ghost sm mt-s\" style=\"width:100%\" id=\"logout\">Sign out</button>`}\n"
)

if OLD in content:
    content = content.replace(OLD, NEW)
    APP.write_text(content, encoding='utf-8')
    print('SUCCESS: guest sign-in button patched')
else:
    print('OLD text not found')
    idx = content.find('Sign out')
    print(repr(content[max(0,idx-100):idx+200]))
    sys.exit(1)
