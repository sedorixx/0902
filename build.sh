#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Basic system packages installieren
apt-get update || true
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    default-jre \
    build-essential \
    curl || true

# Setze grundlegende Umgebungsvariablen
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Erstelle und nutze Arbeitsverzeichnis
WORKDIR="/app"
mkdir -p $WORKDIR
cd $WORKDIR || exit 1

# Erstelle virtuelle Umgebung
python3 -m venv venv || exit 1
. ./venv/bin/activate || exit 1

# Installiere Python-Pakete
pip install --no-cache-dir --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements.txt

# Setze Anwendungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}

# Starte Anwendung
python -m gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
