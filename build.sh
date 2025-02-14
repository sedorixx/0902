#!/bin/bash

echo "PDF Table Extractor - Build und Start Script"
echo "========================================"

# Prüfe Java Installation
if ! command -v java &> /dev/null; then
    echo "Fehler: Java wurde nicht gefunden!"
    echo "Bitte installieren Sie Java mit:"
    echo "brew install java"
    exit 1
fi

# Prüfe Python Installation
if ! command -v python3 &> /dev/null; then
    echo "Fehler: Python wurde nicht gefunden!"
    echo "Bitte installieren Sie Python mit:"
    echo "brew install python3"
    exit 1
fi

# Erstelle virtuelle Umgebung
if [ ! -d "venv" ]; then
    echo "Erstelle virtuelle Python-Umgebung..."
    python3 -m venv venv
fi

# Aktiviere virtuelle Umgebung
source venv/bin/activate

# Installiere Abhängigkeiten
echo "Installiere Abhängigkeiten..."
pip install -r requirements.txt

# Starte die Anwendung
echo
echo "Starte PDF Table Extractor..."
python app.py
