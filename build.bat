@echo off
echo PDF Table Extractor - Build und Start Script
echo ========================================

REM Prüfe Java Installation
java -version >nul 2>&1
if errorlevel 1 (
    echo Fehler: Java wurde nicht gefunden!
    echo Bitte installieren Sie Java von: https://www.java.com/de/download/
    pause
    exit /b 1
)

REM Prüfe Python Installation
python --version >nul 2>&1
if errorlevel 1 (
    echo Fehler: Python wurde nicht gefunden!
    pause
    exit /b 1
)

REM Erstelle virtuelle Umgebung
if not exist venv (
    echo Erstelle virtuelle Python-Umgebung...
    python -m venv venv
)

REM Aktiviere virtuelle Umgebung
call venv\Scripts\activate

REM Installiere Abhängigkeiten
echo Installiere Abhängigkeiten...
pip install -r requirements.txt

REM Starte die Anwendung
echo.
echo Starte PDF Table Extractor...
python app.py

pause
