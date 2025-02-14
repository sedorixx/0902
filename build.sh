#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Prüfe ob sudo verfügbar ist und benutze es falls nötig
if [ "$EUID" -ne 0 ]; then
    if command -v sudo > /dev/null; then
        SUDO=sudo
    else
        echo "Fehler: Dieses Script benötigt Root-Rechte."
        echo "Bitte als Root ausführen oder sudo installieren."
        exit 1
    fi
else
    SUDO=""
fi

# Systemabhängigkeiten installieren mit korrekten Berechtigungen
$SUDO mkdir -p /var/lib/apt/lists/partial
$SUDO chmod 755 /var/lib/apt/lists/partial
$SUDO apt-get clean
$SUDO apt-get update && $SUDO apt-get install -y \
    default-jre \
    python3-pip \
    python3-venv \
    python3-dev \
    build-essential \
    curl

# Stelle sicher, dass Python3 und pip3 verfügbar sind
if ! command -v python3 &> /dev/null; then
    echo "Python3 nicht gefunden. Installation fehlgeschlagen."
    exit 1
fi

if ! command -v pip3 &> /dev/null; then
    echo "pip3 nicht gefunden. Installation fehlgeschlagen."
    exit 1
fi

# Erstelle virtuelle Umgebung mit spezifischem Python-Interpreter
python3 -m venv venv --clear

# Warte kurz auf die Erstellung der venv
sleep 2

# Prüfe ob venv/bin/activate existiert
if [ ! -f "venv/bin/activate" ]; then
    echo "Virtuelle Umgebung konnte nicht erstellt werden"
    exit 1
fi

# Aktiviere virtuelle Umgebung
source venv/bin/activate

# Prüfe ob Aktivierung erfolgreich war
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Virtuelle Umgebung konnte nicht aktiviert werden"
    exit 1
fi

# Aktualisiere pip und installiere wheel
python -m pip install --upgrade pip wheel setuptools

# Installiere Projektabhängigkeiten
pip install -r requirements.txt

# Prüfe ob gunicorn installiert wurde
if ! command -v gunicorn &> /dev/null; then
    echo "Gunicorn wurde nicht korrekt installiert"
    exit 1
fi

# Setze Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Starte die Anwendung
exec gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
