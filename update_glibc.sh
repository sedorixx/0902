#!/bin/bash

# Aktualisiere das System
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:ubuntu-toolchain-r/test
sudo apt-get update
sudo apt-get install -y gcc-9 g++-9 libstdc++6

# Setze gcc-9 als Standard
sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 60 --slave /usr/bin/g++ g++ /usr/bin/g++-9

echo "GLIBC Update abgeschlossen"
