# NEXUS IoT — Public Cloud Deployment & URL Publishing Guide

This guide explains how to publish the **NEXUS IoT** platform to the public internet so users can access both the REST backend and the interactive engineering workstation from any browser worldwide.

---

## Architecture Summary

- **Single Process / Backend-Only**: The Python backend (`run.py` / `nexus.server`) serves both the REST API (`/api/...`, `/ingest/...`) and the single-page web workstation (`web/`) with zero mandatory external runtime dependencies.
- **Port Flexibility**: Binds to `0.0.0.0:$PORT` (automatically respects `PORT` environment variable on Render, Railway, Fly.io, Heroku, AWS).
- **Persistent Data**: SQLite database located at `$NEXUS_DATA_DIR/nexus.db` (auto-seeded on first run with 117 IoT specs).
- **Admin Security**: Super Admin account (Pankaj) is bootstrapped automatically or via `NEXUS_ADMIN_EMAIL` and `NEXUS_ADMIN_PASSWORD`.

---

## Method 1: Deploy to Render.com (Recommended Free Cloud Hosting)

Render provides free cloud hosting with automatic SSL (`https://your-app.onrender.com`) and zero server management.

### Steps:
1. Create a free account at [render.com](https://render.com).
2. Push your `nexus-iot` repository to GitHub or GitLab.
3. In Render dashboard, click **New +** -> **Web Service**.
4. Select your GitHub repository.
5. Render will automatically detect `render.yaml` or you can configure:
   - **Environment**: `Python`
   - **Build Command**: `python -c "print('Build verified')"`
   - **Start Command**: `python run.py`
   - **Plan**: `Free`
6. Add Environment Variables:
   - `PORT`: `10000` (or leave default)
   - `HOST`: `0.0.0.0`
   - `NEXUS_ADMIN_EMAIL`: `admin@nexus.local` (or your email)
   - `NEXUS_ADMIN_PASSWORD`: `<your-secure-password>`
   - `GEMINI_API_KEY`: `<optional-api-key>`
7. Click **Create Web Service**. Within 60 seconds, your public URL will be live at:
   `https://nexus-iot.onrender.com`

---

## Method 2: Deploy to Railway.app

Railway provides automated GitHub deployments with instant HTTPS URLs.

### Steps:
1. Visit [railway.app](https://railway.app) and sign in with GitHub.
2. Click **New Project** -> **Deploy from GitHub repo**.
3. Select `nexus-iot`.
4. Railway will automatically detect the `Procfile` and `Dockerfile`.
5. Under **Settings** -> **Networking**, click **Generate Domain**.
6. Your live public URL will be generated immediately (e.g. `https://nexus-iot.up.railway.app`).

---

## Method 3: Deploy with Docker (Any VPS, DigitalOcean, AWS, GCP)

The included `Dockerfile` builds a lightweight container (< 80 MB):

```bash
# 1. Build the image
docker build -t nexus-iot .

# 2. Run the container on port 8000
docker run -d -p 8000:8000 \
  -e NEXUS_ADMIN_EMAIL="admin@nexus.local" \
  -e NEXUS_ADMIN_PASSWORD="YourPassword123!" \
  -v nexus_data:/app/data \
  --name nexus-iot-app \
  nexus-iot
```

Your app will be accessible at `http://your-server-ip:8000`.

---

## Method 4: Instant Public URL via Cloudflare Tunnel (Right from your machine)

We have bundled `cloudflared.exe` directly in the project directory. You can expose your local server to a public HTTPS URL instantly:

1. Start NEXUS IoT:
   ```bash
   python run.py
   ```
2. In a second terminal, launch the tunnel:
   ```bash
   .\cloudflared.exe tunnel --url http://127.0.0.1:8000
   ```
3. Cloudflare will output an instant, secure public HTTPS URL:
   `https://<random-id>.trycloudflare.com`
4. Anyone on the internet can open that URL to access your live application.

---

## Default Access & Tier Summary

| Tier | Price | Capabilities |
| :--- | :--- | :--- |
| **Super Admin (Pankaj)** | Included | Full platform control, provider configuration, audit logs, unlimited AI |
| **Pro Plan** | **$3.00 / month USD** | Full 117-project library, all 10 Pro tools (Invention Lab, Code Studio, etc.), ad-free |
| **Free Tier** | **$0.00** | 15 flagship beginner projects, basic circuit tools, Google AdMob monetization banner |
