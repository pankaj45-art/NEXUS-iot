FROM python:3.11-slim

LABEL maintainer="Pankaj (Platform Super Admin)"
LABEL description="NEXUS IoT — Connected AI Engineering Platform & Workstation"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=10000 \
    NEXUS_DATA_DIR=/app/data

RUN mkdir -p /app/data

COPY . /app

EXPOSE 10000 8000

CMD ["python", "run.py"]
