#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Setze Basis-Umgebungsvariablen
export HOME=/workspace
export PYTHONUNBUFFERED=1
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

# Erstelle Arbeitsverzeichnis mit korrekten Rechten
mkdir -p $HOME/.local/bin
export PATH="$HOME/.local/bin:$PATH"

# Installiere Python ohne apt
cd $HOME
curl -O https://www.python.org/ftp/python/3.9.16/Python-3.9.16.tgz
tar xzf Python-3.9.16.tgz
cd Python-3.9.16
./configure --enable-optimizations --prefix=$HOME/.local
make -j4
make install

# Setze Python-Pfade
export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$HOME/.local/lib/python3.9/site-packages"

# Installiere pip
curl -sS https://bootstrap.pypa.io/get-pip.py | $HOME/.local/bin/python3

# Installiere Requirements
$HOME/.local/bin/pip3 install --user -r requirements.txt

# Starte die Anwendung
exec $HOME/.local/bin/python3 -m gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 4 --timeout 120
