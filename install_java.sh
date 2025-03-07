#!/bin/bash

echo "Starting Java installation..."

# Update package list
apt-get update

# Install default JDK and JRE
apt-get install -y default-jre default-jdk

# Verify installation
java -version
javac -version

echo "Java installation complete!"
