#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
pip install playwright==1.40.0
playwright install --with-deps chromium

echo "Build complete!"
