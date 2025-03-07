#!/bin/bash

# Alte Java-Version entfernen
sudo apt remove -y default-jdk openjdk-11-jdk

# Repository für neue Java-Version
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:openjdk-r/ppa
sudo apt update

# OpenJDK 17 installieren
sudo apt install -y openjdk-17-jdk

# JVM-Speicher-Konfiguration
echo "export _JAVA_OPTIONS='-Xmx4G -Xms2G'" >> ~/.bashrc
echo "export JAVA_TOOL_OPTIONS='-XX:+UseG1GC -XX:MaxGCPauseMillis=100'" >> ~/.bashrc

source ~/.bashrc

echo "Java Setup abgeschlossen"
