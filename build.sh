#!/bin/bash

echo "PDF Table Extractor - Koyeb Build Script"
echo "======================================"

# Setze Basis-Umgebung
export HOME="/app"
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export PYTHONUNBUFFERED=1
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
unset PYTHONPATH
unset PYTHONHOME

# Erstelle und bereite Arbeitsverzeichnis vor
mkdir -p $HOME
cd $HOME

# Installiere Python direkt von python.org
curl -O https://www.python.org/ftp/python/3.9.16/Python-3.9.16.tgz && \
tar xzf Python-3.9.16.tgz && \
cd Python-3.9.16 && \
./configure --enable-optimizations --prefix=$HOME/.local && \
make -j4 && \
make install

# Setze Python-Pfade
export PATH="$HOME/.local/bin:$PATH"

# Installiere pip
curl -sSL https://bootstrap.pypa.io/get-pip.py | $HOME/.local/bin/python3.9

# Installiere Requirements direkt (ohne venv)
$HOME/.local/bin/pip3.9 install --no-cache-dir -r /app/requirements.txt

# Starte Anwendung
cd /app
exec $HOME/.local/bin/python3.9 -m gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 4 --timeout 120
