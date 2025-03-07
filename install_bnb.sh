#!/bin/bash

# Aktualisiere Transformers
pip install "transformers>=4.45.1"

# Installiere Intel Extension für PyTorch
pip install intel_extension_for_pytorch

# Installiere optimiertes bitsandbytes
pip install --force-reinstall 'https://github.com/bitsandbytes-foundation/bitsandbytes/releases/download/continuous-release_multi-backend-refactor/bitsandbytes-0.44.1.dev0-py3-none-manylinux_2_24_x86_64.whl' --no-deps

echo "Installation abgeschlossen"
