#!/bin/bash
pkill -f uvicorn
export GOOGLE_APPLçICATION_CREDENTIALS="/Users/skyfalling/Workspace/cloud/liteblog/credentials.json"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000