#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Installiere grundlegende Unix-Tools
apt-get update && apt-get install -y \
    git \
    sed \
    coreutils \
    build-essential \
    python3.9 \
    python3-pip \
    default-jre \
    curl

# Setze Umgebungsvariablen
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"
export PYTHONUNBUFFERED=1
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# Erstelle und aktiviere virtuelle Umgebung
python3 -m venv venv
. ./venv/bin/activate

# Installiere Python-Abhängigkeiten
pip install --no-cache-dir -r requirements.txt

# Starte die Anwendung
exec python -m gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 4 --timeout 120
