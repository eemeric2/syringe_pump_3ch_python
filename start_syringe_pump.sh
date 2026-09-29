#!/bin/bash

# Syringe Pump GUI startup script for Raspberry Pi

# Get the script directory (root of repo)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Python 3 not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y python3 python3-pip python3-tk
fi

# Check for required packages
python3 -c "import serial" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "Installing pyserial..."
    pip3 install pyserial
fi

# Run the GUI from repo root
cd "$SCRIPT_DIR"
python3 syringe_pump_3ch_python.py > /tmp/pump_monitor.log 2>&1 &
disown
exit 0
