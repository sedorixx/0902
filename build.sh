#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Systemabhängigkeiten installieren
apt-get update && apt-get install -y \
    default-jre \
    python3-pip \
    python3-venv \
    build-essential \
    curl

# Erstelle virtuelle Umgebung
python3 -m venv venv

# Aktiviere virtuelle Umgebung
source venv/bin/activate

# Aktualisiere pip
pip install --upgrade pip

# Installiere Projektabhängigkeiten
pip install -r requirements.txt

# Setze Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}

# Starte die Anwendung
gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
