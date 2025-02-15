#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Add deadsnakes PPA und installiere Python 3.9
apt-get update && apt-get install -y software-properties-common && \
add-apt-repository -y ppa:deadsnakes/ppa && \
apt-get update && \
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.9 \
    python3.9-dev \
    python3.9-distutils \
    python3.9-venv \
    python3-pip \
    default-jre \
    build-essential \
    curl \
    locales

# Setze Locale
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8

# Konfiguriere Python-Umgebung
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8
unset PYTHONPATH
unset PYTHONHOME

# Installiere pip für Python 3.9
curl -sS https://bootstrap.pypa.io/get-pip.py | python3.9

# Erstelle und aktiviere venv
cd /tmp
python3.9 -m venv venv
. ./venv/bin/activate

# Installiere Abhängigkeiten
pip install --no-cache-dir --upgrade pip setuptools wheel
pip install --no-cache-dir -r /app/requirements.txt

# Wechsle ins App-Verzeichnis
cd /app

# Starte Anwendung
exec /tmp/venv/bin/gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 4 --timeout 120
