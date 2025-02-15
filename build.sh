#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Versuche root-Rechte zu erhalten
if [ "$EUID" -ne 0 ]; then 
    exec sudo "$0" "$@"
fi

# System-Pakete installieren
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y software-properties-common
add-apt-repository -y ppa:deadsnakes/ppa
apt-get update
apt-get install -y \
    python3.9 \
    python3.9-venv \
    python3.9-dev \
    python3-pip \
    default-jre \
    build-essential \
    curl

# Python-Umgebung konfigurieren
export PYTHONUNBUFFERED=1
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Arbeitsverzeichnis erstellen und Berechtigungen setzen
mkdir -p /app
chown -R www-data:www-data /app
chmod -R 755 /app
cd /app

# Virtuelle Umgebung erstellen
python3.9 -m venv venv
chown -R www-data:www-data venv
chmod -R 755 venv

# Als www-data-User ausführen
su www-data << 'EOF'
source venv/bin/activate
pip install --no-cache-dir --upgrade pip setuptools wheel
pip install --no-cache-dir -r requirements.txt

export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}

exec venv/bin/gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
EOF
