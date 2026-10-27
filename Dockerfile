FROM python:3.11-slim

LABEL maintainer="Pankaj (Platform Super Admin)"
LABEL description="NEXUS IoT — Connected AI Engineering Platform & Workstation"

WORKDIR /app

# Ensure unbuffered Python output
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV HOST=0.0.0.0
ENV PORT=8000
ENV NEXUS_DATA_DIR=/app/data

# Create data directory
RUN mkdir -p /app/data

# Copy application source code
COPY . /app

# Remove local binaries if present
RUN rm -f /app/cloudflared.exe

EXPOSE 8000

# Healthcheck for container orchestration
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request, os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/health')" || exit 1

CMD ["python", "run.py"]
