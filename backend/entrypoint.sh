#!/bin/sh
set -e
echo "== APTG backend startup =="
cd /srv
python3 db/apply_schema.py
python3 db/seed.py
echo "== Starting API server =="
cd /srv/backend
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
