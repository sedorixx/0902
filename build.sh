#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"


# Installiere pip und Abhängigkeiten
pip install -r requirements.txt

# Setze Umgebungsvariablen
export FLASK_APP=app.py
export FLASK_ENV=production
export PORT=${PORT:-8080}
export PYTHONIOENCODING=utf-8
export LC_ALL=C.UTF-8
export LANG=C.UTF-8
export PYTHONDONTWRITEBYTECODE=1

# Starte die Anwendung
exec python -m gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
