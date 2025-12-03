#!/usr/bin/env bash
# Render build script

set -o errexit

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Chrome and Chromedriver for Selenium
apt-get update
apt-get install -y wget unzip

# Install Chromium
apt-get install -y chromium chromium-driver

# Verify installation
chromium --version
chromedriver --version

echo "Build complete!"
