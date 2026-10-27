# NEXUS IoT — Live Engineering Wallpaper Update

This package builds on the existing NEXUS IoT Engineering Upgrade archive. It adds a continuously animated, locally hosted engineering wallpaper with an arc-reactor-inspired core, drifting blueprint grid, subtle scan sweep, moving signal particles, and slow cyan/violet light transitions.

## Install
1. Extract this ZIP to a new folder (keep a backup of your current NEXUS folder).
2. Open the `nexus-iot` folder in Command Prompt.
3. Run `python run.py`.
4. Open `http://localhost:8000` and refresh with Ctrl+F5 if the old CSS is cached.

The wallpaper is served from the app's own `web/engineering-wallpaper.svg` asset and does not require an external image or animation service. The motion respects `prefers-reduced-motion`. Main application panels remain layered above the wallpaper for readability.

## Changed files
- `web/index.html`: cache-bust versions updated.
- `web/app.js`: adds the wallpaper layer to the existing authenticated application shell.
- `web/app.css`: animated background, blueprint grid, scan sweep, particles, and reduced-motion fallback.
- `web/engineering-wallpaper.svg`: adds subtle motion to the reactor rings.

This is a visual enhancement; it does not imply hardware simulation or AI-generated circuits are verified.
