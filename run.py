#!/usr/bin/env python3
"""NEXUS IoT - development/production entry point.

    python3 run.py

Environment: PORT, HOST, NEXUS_DATA_DIR, NEXUS_SECRET, OPENAI_API_KEY,
STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID, ...
See README.md for the full list and the admin bootstrap procedure.
"""
from nexus.server import main

if __name__ == "__main__":
    main()
