#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Arbeitsverzeichnis erstellen und nutzen
mkdir -p /app
cd /app

# Python-Umgebung konfigurieren
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# System-Dependencies installieren
apt-get update
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    default-jre \
    curl \
    build-essential

# Erstelle virtuelle Umgebung im aktuellen Verzeichnis
python3 -m venv venv

# Aktiviere virtuelle Umgebung
. ./venv/bin/activate

# Upgrade pip und installiere Abhängigkeiten
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

# Setze Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}

# Starte die Anwendung
exec python -m gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
