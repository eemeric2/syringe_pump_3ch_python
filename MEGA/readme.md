# 3-Channel Syringe Pump Controller

Arduino-based syringe pump system with Python GUI for precise fluid delivery control. Designed for behavioral neuroscience experiments with real-time monitoring and logging.

## Features

- **3 Independent Pumps**: Individual control of 3 stepper motor-driven syringe pumps
- **Hardware Triggers**: External trigger input from TDT/Plexon systems via GPIO pins
- **Serial Commands**: Full command-line interface for automation
- **Python GUI**: Real-time monitoring, statistics, and manual control
- **Position Tracking**: Automatic plunger position monitoring with boundary detection
- **Direction Reversal**: Auto-reverse at 0-40mm travel limits
- **Data Logging**: Activity log with CSV export and persistent state storage
- **Simulation Mode**: Test GUI without hardware triggers

## Hardware Requirements

### Arduino
- Arduino Mega 2560
- USB connection to host computer

### Stepper Motors & Drivers
- 3x stepper motors (NEMA 17 or compatible)
- 3x stepper drivers (DRV8825, A4988, or similar)
- Power supply (12-24V depending on motor specs)

### Syringe Pumps
- 3x syringe pump assemblies (0-40mm travel recommended)
- Mechanical coupling between stepper motor and plunger

### External Trigger Input
- 8-bit GPIO input (pins 2-9)
- Pin 9: Trigger (rising edge)
- Pins 2-8: Command encoding

## Pin Configuration
### Arduino Mega Pinout

**GPIO Input (from external device):**
```yaml
Pin 2: Amount bit 0 (LSB)
Pin 3: Amount bit 1
Pin 4: Amount bit 2
Pin 5: Amount bit 3 (MSB)
Pin 6: Reserved
Pin 7: Pump select bit 0
Pin 8: Pump select bit 1
Pin 9: Trigger (rising edge)
```

**Stepper Motor Control:**
```yaml
Pump 1: Enable=10, Step=11, Direction=12
Pump 2: Enable=13, Step=14, Direction=15
Pump 3: Enable=16, Step=17, Direction=18
```
**LED:**
```yaml
Pin 13 (built-in): Trigger indicator
```
## Bit Encoding (External Triggers)

### Amount (Bits 0-3)
- Value 0-15 representing delivery amounts 1-16 units
- Calculated as: `magnitude = (bits_0_3) + 1`

### Pump Selection (Bits 5-6)
```yaml
10 = Pump 1
01 = Pump 2
11 = Pump 3
```
```shell
### Trigger (Bit 7)
- Rising edge triggers delivery

### Example Encodings
Pump 1, Amount 1:  00000101 (binary)
Pump 1, Amount 2:  10000101 (binary)
Pump 2, Amount 1:  00000011 (binary)
Pump 3, Amount 5:  00100111 (binary)
```
## Installation

### Arduino Setup

1. **Install Arduino IDE** (version 1.8.x or later)
2. **Open syringe_pump_3ch_MEGA.ino** in Arduino IDE
3. **Select Board**: Tools → Board → Arduino Mega 2560
4. **Select Port**: Tools → Port → COM# (your Arduino)
5. **Upload**: Sketch → Upload

### Python Setup

1. **Install Python 3.10+** on your system
2. **Install dependencies**:
  
```bash
pip install pyserial
```

Tkinter usually comes with Python, but on Linux you may need:

```bash
sudo apt-get install python3-tk
```
3. Run the GUI:
```bash
python syringe_pump_3ch_python.py
```
### Usage
#### GUI Application
Connection

1. Select COM port from dropdown
2. Set Baud rate to **115200** (default) 
3. Click "Connect"
4. Wait for "Connected" status (green)

Manual Control

- **Desired µL**: Set unit size per delivery (1-500 µL recommended)
- **Trigger Count**: Shows number of triggers received
- **Plunger Positions**: Real-time position display with progress bars
- **Set Position**: Manually set pump position and direction

Statistics

- **Triggers**: Number of times pump was triggered
- **Total Units**: Sum of all delivery amounts
- **Delivered µL**: Actual volume per unit (based on desired µL)
- **Total µL**: Cumulative delivered volume

Simulation Mode

- **Simulate Input**: Generate random triggers for testing (no hardware needed)
-- Useful for GUI testing without external device
  
Data Management

- Reset Stats: Clear counters (positions preserved)
- Export CSV: Save statistics to CSV file
- Clear Log: Clear activity log (on-screen only)

#### Serial Commands
The previous version of this project was run using the Serial Monitor of the Arduino IDE. **The Tkinter user interface is not necessary to control the syringe pumps**
All the functionality of the GUI can be implemented using only the serial commands from the Serial Monitor.
However the log and state files are only created using the GUI. 

**If using the Serial Monitor, the positions of the 3 pumps must be set to reflect the actual pump positions on the hardware before you start your experiment.** 

All commands start with **!** and end with **\r\n**

**If your Serial Monitor is showing unreadable "gibberish" characters or nothing at all, verify the following settings at the bottom or corner of the monitor panel:**
- **Baud Rate**: This drop-down menu controls the communication speed.
It must exactly match the number in your code (e.g., Serial.begin(9600)
means the monitor must be set to 9600 baud).
- **Line Ending**: When you type a command and hit send, this determines if hidden
characters like a newline **(\n / LF)** or carriage return **(\r / CR)** are attached. Set it to No line ending or Newline depending on how your code handles incoming data.
- **Autoscroll**: Checking this option forces the window to scroll down automatically
  as new data pours in.
  

Position & Movement

```scss
!GetCurrentPosition [pump]           Get position of pump (1-3)
!SetCurrentPosition [pump] [pos]     Set position in mm (0-40)
!SetDirection [pump] [F/R]           Set direction (F=Forward, R=Reverse)
!Translate [pump] [distance]         Move ±distance in mm
!Home [pump]                         Move to position 0
```

Unit Size & Calibration

```scss
!GetUnitSize [pump]                  Get unit size in µL
!SetUnitSize [pump] [size]           Set unit size in µL
!SetCalibration [pump] [ppm]         Set pulses per mm (default 945)
```
Manual Triggers

```scss
!ManualReward [pump]                 Deliver one unit manually
!ManualTrigger [pump] [amount]       Deliver specific amount (1-16 units)
```

Status & Counters

```scss
!GetStatus                           Get full system status (JSON)
!ResetCounter [pump]                 Reset trigger count and volume
```

Debug

```scss
!TestDirection [pump]                Toggle direction pin 5 times (test only)
```

#### Example Python Script
**Connecting and executing the serial commands via Python is also an option**
```python
import serial
import time

# Connect to Arduino
ser = serial.Serial('COM5', 115200, timeout=1)
time.sleep(2)  # Wait for Arduino initialization

# Set unit size to 50 µL
ser.write(b"!SetUnitSize 1 50\r\n")
time.sleep(0.1)

# Manually trigger pump 1 with amount 5
ser.write(b"!ManualTrigger 1 5\r\n")
time.sleep(0.5)

# Get status
ser.write(b"!GetStatus\r\n")
response = ser.readline().decode('utf-8')
print(response)

ser.close()
```
#### Calibration
##### Measuring Pulses Per MM
1. **Set position to 0: !Home 1**
2. **Deliver known volume: !Translate 1 10** (move 10mm)
3. **Count motor pulses**: Measure with oscilloscope or motor counter
4. **Calculate: ppm = pulses / distance_mm**
5. **Set calibration: !SetCalibration 1 [ppm]**

   Default: 945 pulses/mm (for typical NEMA 17 at 1/8 microstepping)

**EXTREME CAUTION SHOULD BE EXERCISED USING THE CALIBRATION ROUTINES. INCORRECT SETTINGS CAN LEAD TO HARDWARE DAMAGE**

##### Volume Verification

1. Set unit size: !SetUnitSize 1 100 (100 µL)
2. Dispense into graduated cylinder: !ManualReward 1
3. Measure actual volume
4. Adjust unit size: If 80 µL delivered but set for 100 µL:
-- New size = 100 × (100/80) = 125 µL

### Troubleshooting
#### Serial Connection Issues
- **"Unexpected data format"**: Baud rate mismatch. Set to 115200.
- **"Connection timeout"**: Check USB cable and COM port selection
- **Garbage characters**: Baud rate is wrong

#### Motor Not Moving
- **Verify pin assignments** in code match your wiring
- **Check stepper driver power**: Should be 12-24V
- **Test with oscilloscope**: Enable and step pins should toggle

#### Direction Pin Not Toggling
- **Removed GPIO polling from pulse loop** (fixed in v2.1)
- **Verify pin 12/15/18 connections** for pump 1/2/3
- Test with **!TestDirection command**

#### Position Tracking Off
- **Run calibration procedure** to set correct pulses/mm
- **Check boundary detection** (should reverse at 40mm)
- **Verify Arduino is receiving position updates**

### File Structure
```css
syringe_pump_3ch_python/
├── syringe_pump_3ch_python.py       Main Python GUI application
├── README.md                         This file
├── pump_state.json                  Persisted pump configuration
├── PumpMonitorLogs/
│   └── pump_log_YYYYMMDD_HHMMSS.txt Activity logs
└── MEGA/
    └── syringe_pump_3ch_MEGA.ino    Arduino sketch
```

### Data Files
#### pump_state.json

Stores pump configuration between sessions:

- Current position (mm)
- Direction (Forward/Reverse)
- Desired unit size (µL)
- Desired µL change history with timestamps

#### CSV Export

Exports current statistics:

- Pump number
- Trigger count
- Total units delivered
- Desired µL per unit
- Delivered µL per unit
- Total µL delivered
- Current position
- Direction

### Safety Considerations
- Mechanical Limits: System enforces 0-40mm boundaries
- Motor Current: Verify stepper driver current limit is appropriate
- Emergency Stop: Disconnect USB or power to stop immediately
- Fluid Management: Ensure appropriate disposal of delivered fluid

### Performance Specifications
- **Resolution**: 0.04 mm per motor step (adjustable via calibration)
- **Accuracy**: ±0.1 mm with proper calibration
- **Speed**: Up to 1000 steps/second (adjustable via timing constants)
- **Trigger Response**: <100 ms from trigger to motor movement
- **Baud Rate**: 115200 (fixed, no configuration needed)
- **Update Rate**: Real-time (limited by serial communication) 

### Known Limitations
- **No simultaneous pump operation**: Pumps controlled sequentially
- **No temperature compensation**: Calibration assumed at room temperature
- **Single-threaded Arduino**: High-speed triggers may be dropped during motor operation
- **CSV export history**: Desired µL history resets on new connection (TODO)

## Version History
### v2.1 (Current)
- Added **!SetDirection** command for manual direction control
- Fixed direction pin toggling issue in GUI mode
- Auto-sync position/direction from Arduino on each delivery
- Improved serial communication timing and buffering
- Position manually settable with direction control

### v2.0
- Fixed bit mapping for pump/amount decoding
- Fixed serial communication (baud rate, UTF-8 encoding)
- Added desired µL tracking history
- Implemented !ManualTrigger command for simulation mode

### v1.0
- Initial release
- Basic 3-pump control
- Python GUI with statistics

## Future Enhancements
 - [ ] CSV export with desired µL history
 - [ ] Interrupt-based trigger handling for dropped trigger detection
 - [ ] Raspberry Pi deployment with desktop shortcuts
 - [ ]  Multi-pump simultaneous operation
 - [ ]  Real-time graphing of delivery history
 - [ ]  Network remote control capability

## Support & Contributing
For issues, feature requests, or contributions:

1. Check existing documentation and troubleshooting
2. Review Arduino serial monitor output for error messages
3. Document your setup and reproduction steps
4. Share relevant configuration (pins, motor specs, calibration values)

## License

MIT License

Copyright (c) 2026 Johns Hopkins University - Zanvyl Krieger Mind/Brain Institute

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, and sublicense, subject to
the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

See LICENSE file for full terms.

## Acknowledgments
Developed for the Stuphorn Lab at the Zanvyl Krieger Mind/Brain Institute of Johns Hopkins University.

Last Updated: September 2026
Maintainer: [Erik E. Emeric]
Contact: [eee@jhu.edu]





