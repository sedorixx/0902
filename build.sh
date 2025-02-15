#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Python-Basis installieren
apt-get update && apt-get install -y \
    python3.9 \
    python3.9-dev \
    python3.9-venv \
    python3-pip \
    default-jre \
    build-essential \
    curl

# Setze Python 3.9 als Standard
update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.9 1
update-alternatives --set python3 /usr/bin/python3.9

# Setze essentielle Umgebungsvariablen
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
export PYTHONIOENCODING=utf-8
unset PYTHONPATH
unset PYTHONHOME

# Erstelle und aktiviere virtuelle Umgebung
python3 -m venv --copies /app/venv
. /app/venv/bin/activate

# Installiere Basis-Pakete
/app/venv/bin/pip install --no-cache-dir -U pip setuptools wheel

# Installiere Projektabhängigkeiten
/app/venv/bin/pip install --no-cache-dir -r requirements.txt

# Setze weitere Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}

# Starte die Anwendung
exec /app/venv/bin/python -m gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
