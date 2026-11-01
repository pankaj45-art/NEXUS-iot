"""Patch hashchange listener to work for guests too."""
import sys
from pathlib import Path

APP = Path(__file__).parent.parent / 'web' / 'app.js'
content = APP.read_text(encoding='utf-8')

OLD = "window.addEventListener('hashchange', () => { if (state.me) renderRoute(); else boot(false); });\n"
NEW = "window.addEventListener('hashchange', () => { if (state.me) renderRoute(); else boot(false); });\n"

# Check if it's already fine
if OLD in content:
    print('hashchange listener already correct')
else:
    print('Not found, checking:')
    idx = content.find('hashchange')
    print(repr(content[idx:idx+200]))
