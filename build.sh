#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Python-Umgebungsvariablen korrigieren
unset PYTHONPATH
unset PYTHONHOME

# Python 3.9 explizit installieren
curl -O https://www.python.org/ftp/python/3.9.16/Python-3.9.16.tgz
tar -xzf Python-3.9.16.tgz
cd Python-3.9.16
./configure --enable-optimizations
make -j $(nproc)
make install
cd ..
rm -rf Python-3.9.16*

# Setze Python 3.9 als Standard
update-alternatives --install /usr/bin/python3 python3 /usr/local/bin/python3.9 1

# Erstelle benötigte Verzeichnisse mit korrekten Rechten
mkdir -p $HOME/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# Erstelle virtuelle Umgebung
python3.9 -m venv venv

# Aktiviere virtuelle Umgebung
source venv/bin/activate

# Installiere pip und Abhängigkeiten
python -m pip install --upgrade pip setuptools wheel
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
