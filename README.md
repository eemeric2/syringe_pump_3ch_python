# syringe_pump_3ch_python
3 channel syringe pump controller
# 3-Channel Syringe Pump Monitor

A Python GUI application for monitoring and logging Arduino-controlled syringe pumps with real-time volume tracking and plunger position management.

## Features

### Core Functionality
- **Real-time Serial Monitoring**: Connects to Arduino via serial port to decode pump control signals
- **3-Channel Pump Support**: Monitors up to 3 independent syringe pumps simultaneously
- **Discrete Volume Calculation**: Automatically calculates deliverable volumes based on pump mechanics (8.0 µL/step)
- **Plunger Position Tracking**: Visual progress bars showing current position (0-40 mm travel range)
- **Auto-reversal**: Pumps automatically reverse direction at travel boundaries

### Data Management
- **State Persistence**: Saves pump positions and statistics between sessions (`pump_state.json`)
- **Activity Logging**: Color-coded log with timestamps for all pump events
- **CSV Export**: Export complete pump statistics to timestamped CSV files
- **Auto-save**: Logs automatically saved to `./PumpMonitorLogs/` on exit

### Simulation & Testing
- **Simulation Mode**: Built-in random trigger generator for testing without hardware
- **Parity Constraint Enforcement**: Ensures valid pump/magnitude combinations
- **LED Trigger Indicator**: Visual feedback for pump activation events

## Hardware Requirements

### Arduino Pin Configuration
- **Pins 2-5**: 4-bit magnitude encoding (binary LSB on Pin 2)
- **Pins 6-7**: Pump selection encoding (1/2/3)
- **Pin 8**: Trigger input (INPUT_PULLUP, rising edge detection)

### Pump Mechanics
- **Step Resolution**: 0.04 mm/step
- **Volume per mm**: 0.20 mL/mm
- **Discrete Volume**: 8.0 µL/step
- **Maximum Travel**: 40.0 mm

## Installation

### Prerequisites
```bash
pip install pyserial
```
### Python Version
- Python 3.x with tkinter (usually included)

### Usage
#### Starting the Application
```bash
python syringe_pump_3ch_python.py
```
#### Connecting to Arduino
- Select serial port from dropdown (or click Refresh to update list)
- Choose baud rate (default: 9600)
- Click "Connect"
#### Simulation Mode
- Click "Simulate Input: OFF" to toggle simulation on
- Generates random pump triggers every 2 seconds

Useful for testing logic without hardware

#### Setting Desired Volumes
- Enter desired volume (µL) in the "Desired µL" column
- Press Enter to update
- "Delivered µL" shows actual deliverable volume (rounded to nearest 8 µL step)
- Manual Position Adjustment
- Click "Set Position" next to any pump
- Enter new position (0-40 mm)
- Useful for synchronizing software with physical plunger position
  
#### Exporting Data
- Click "Export CSV" to save statistics with timestamp
- Format: **pump_stats_YYYYMMDD_HHMMSS.csv**
- Includes triggers, units, desired/delivered/total volumes

### File Structure
```python
./
├── syringe_pump_3ch_python.py    # Main application
├── pump_state.json                # Persistent state file
└── PumpMonitorLogs/               # Auto-created log directory
    ├── pump_log_YYYYMMDD_HHMMSS.txt
    └── pump_stats_YYYYMMDD_HHMMSS.csv
```
### Signal Encoding
#### Bit String Format (7 bits)
```makefile
Index:  0    1    2         3         4         5         6
Bit:   [0] [0] [Pump0] [Pump1] [Mag2] [Mag1] [Mag0]
                └─────┬─────┘  └──────┬──────┘
                   Pump (2 bits)    Magnitude (4 bits)
```

### Pump Encoding
- 01 → Pump 1
` 10 → Pump 2
- 11 → Pump 3
- 00 → Invalid (logged as error)
#### Magnitude Encoding
- 4-bit binary (0-15) representing units 1-16
- LSB at index 6, MSB at index 4
#### Parity Constraint
- **Critical**: Index 3 is shared between pump encoding and magnitude encoding
- Pump 1/3 (bit[3]='1') → Requires EVEN magnitudes
- Pump 2 (bit[3]='0') → Requires ODD magnitudes
- Simulation mode automatically enforces this constraint
  
### Statistics Display
#### Per-Pump Metrics
- Triggers: Total number of activation events
- Total Units: Cumulative unit count from magnitude values
- Desired µL: User-specified volume per unit
- Delivered µL: Actual deliverable volume (discrete steps)
- Total µL: Cumulative volume delivered
#### Color Coding
- Pump 1: Blue
- Pump 2: Green
- Pump 3: Purple
### Troubleshooting
#### Connection Issues
- Ensure Arduino is plugged in and powered
- Check correct COM port selection
- Verify baud rate matches Arduino sketch (default 9600)
- On Linux, may need permissions: **sudo usermod -a -G dialout $USER**
#### Focus Issues on Launch
- If Entry fields don't respond initially, click window title bar
- Fixed in current version with cross-platform focus management
- Invalid Pump Readings
- Check Arduino wiring matches pin configuration
- Verify INPUT_PULLUP mode on Arduino Pin 8
- Use simulation mode to verify software decoding logic

### License
- MIT License - Feel free to modify and distribute

### Author
eee@jhu.edu

Developed for the Stuphorn Lab precision syringe pump control and monitoring applications
