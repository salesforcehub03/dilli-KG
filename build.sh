#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Starting build process..."

# Install dependencies from requirements.txt
pip install -r requirements.txt

echo "Build process completed successfully."
