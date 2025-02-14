# PDF Table Extractor

## Projektbeschreibung
Dieses Projekt verwendet pdfplumber, um PDF-Dateien zu analysieren und zu verarbeiten.

## Voraussetzungen

- Python 3.8 oder höher
- Java Runtime Environment (JRE) Version 8 oder höher
  - Windows: [Java JRE Download](https://www.java.com/de/download/)
  - Linux: `sudo apt install default-jre`
  - MacOS: `brew install java`
- Pip (Python Package Installer)

## Installation

### 1. Java Installation prüfen
```bash
java -version
```
Falls Java nicht installiert ist, bitte zuerst Java installieren.

### 2. Python Umgebung einrichten
```bash
# Virtuelle Umgebung erstellen
python -m venv venv

# Virtuelle Umgebung aktivieren
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Abhängigkeiten installieren
pip install -r requirements.txt
```

## Anwendung starten

```bash
python app.py
```

Die Anwendung ist dann unter http://localhost:5000 erreichbar.

## Fehlerbehebung

### Java nicht gefunden
Falls die Fehlermeldung "Java nicht gefunden" erscheint:
1. Stellen Sie sicher, dass Java installiert ist
2. Fügen Sie Java zum System PATH hinzu
3. Starten Sie die Anwendung neu