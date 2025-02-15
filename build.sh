#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Python-Umgebung konfigurieren
export PYTHONUNBUFFERED=1
unset PYTHONPATH
unset PYTHONHOME

# System-Python installieren
apt-get update && apt-get install -y \
    python3.9 \
    python3.9-venv \
    python3.9-dev \
    python3-pip

# Erstelle und aktiviere virtuelle Umgebung
python3.9 -m venv /app/venv
. /app/venv/bin/activate

# Installiere pip Abhängigkeiten
/app/venv/bin/pip install --upgrade pip setuptools wheel
/app/venv/bin/pip install -r requirements.txt

# Setze Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export PYTHONPATH=/app
export PATH="/app/venv/bin:$PATH"

# Starte die Anwendung
exec /app/venv/bin/python -m gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
