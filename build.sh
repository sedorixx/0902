#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Setze HOME wenn nicht definiert
if [ -z "$HOME" ]; then
    export HOME=/root
fi

# Erstelle benötigte Verzeichnisse mit korrekten Rechten
mkdir -p $HOME/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# Python und pip ohne root installieren
curl -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py --user
rm get-pip.py

# Erstelle virtuelle Umgebung im Benutzerverzeichnis
python3 -m venv $HOME/venv

# Aktiviere virtuelle Umgebung
source $HOME/venv/bin/activate

# Aktualisiere pip und installiere grundlegende Pakete
pip install --upgrade pip setuptools wheel

# Installiere Projektabhängigkeiten
pip install --user -r requirements.txt

# Setze Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8

# Starte die Anwendung
python3 -m gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
