#!/bin/bash
pkill -f uvicorn || true
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
