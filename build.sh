#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Setze Arbeitsverzeichnis
WORKDIR="/workspace"
mkdir -p $WORKDIR
cd $WORKDIR

# Setze Benutzerrechte
export HOME=$WORKDIR
chmod -R 755 $WORKDIR

# System-Pakete installieren ohne apt cache
rm -rf /var/lib/apt/lists/*
apt-get clean
apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.9 \
    python3.9-venv \
    python3.9-dev \
    default-jre \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python-Umgebung konfigurieren
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
unset PYTHONPATH
unset PYTHONHOME

# Virtuelle Umgebung im Arbeitsverzeichnis erstellen
python3.9 -m venv $WORKDIR/venv
source $WORKDIR/venv/bin/activate

# Pip aktualisieren und Abhängigkeiten installieren
$WORKDIR/venv/bin/pip install --no-cache-dir --upgrade pip setuptools wheel
$WORKDIR/venv/bin/pip install --no-cache-dir -r requirements.txt

# Anwendungsvariablen setzen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}

# Start der Anwendung
exec $WORKDIR/venv/bin/gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
