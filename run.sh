#!/bin/bash
# Convenience script to run the application with the virtual environment

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Virtual environment not found. Creating one..."
    python -m venv "$SCRIPT_DIR/venv"
    echo "Installing dependencies..."
    "$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

"$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/main.py"
