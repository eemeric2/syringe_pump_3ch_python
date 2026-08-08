# 3-Channel Syringe Pump Monitor - Raspberry Pi with GRBL

A Python GUI application for Raspberry Pi that monitors GPIO trigger inputs and controls 3 syringe pumps via GRBL-based stepper motor controller.

## Features

### Core Functionality
- **GPIO Trigger Detection**: Reads 7-bit encoded signals from GPIO pins using hardware interrupts
- **GRBL Motor Control**: Sends G-code commands to control 3 independent stepper motors (X/Y/Z axes)
- **Real-time Position Tracking**: Queries GRBL status every 500ms for actual motor positions
- **Discrete Volume Calculation**: Automatically rounds to deliverable volumes (8.0 µL/step)
- **Auto-reversal**: Pumps reverse direction at 0mm and 40mm limits while dispensing full volume
- **Response Time Monitoring**: Tracks trigger-to-command delay for each pump

### Data Management
- **State Persistence**: Saves positions, directions, and statistics between sessions (`pump_state_pi.json`)
- **Activity Logging**: Color-coded log with timestamps for triggers, commands, and system events
- **CSV Export**: Export pump statistics to timestamped CSV files
- **Auto-save**: Logs saved to `./PumpMonitorLogs/` on exit

### Testing & Calibration
- **Simulation Mode**: Random trigger generator for testing without hardware (2-second intervals)
- **Parity Constraint Enforcement**: Ensures valid pump/magnitude combinations in simulation
- **LED Trigger Indicator**: Visual feedback for pump activation events

## Hardware Requirements

### Raspberry Pi Setup
- **Model**: Raspberry Pi 4 Model B (Bookworm OS)
- **GPIO Pins** (BCM numbering):
GPIO 17 → Bit 0 (Magnitude LSB)
GPIO 18 → Bit 1 (Magnitude)
GPIO 27 → Bit 2 (Magnitude)
GPIO 22 → Bit 3 (Magnitude MSB / Pump bit overlap)
GPIO 23 → Bit 4 (Pump bit)
GPIO 24 → Bit 5 (Pump bit)
GPIO 25 → Bit 6 (Trigger input)

```markdown
*Note: Avoids GPIO 2/3 for I2C touchscreen compatibility*
```
### GRBL Controller
- **Hardware**: Arduino with GRBL firmware + Longruner Nema 17 Stepper Motor CNC Kit
- **Connection**: USB serial to Raspberry Pi
- **Baud Rate**: 115200 (recommended)
- **Axis Mapping**:
- Pump 1 → X-axis
- Pump 2 → Y-axis
- Pump 3 → Z-axis

### Signal Encoding
- **7-bit format** (same as Arduino version):
- Bits 0-3: Magnitude (4-bit binary, 1-16 units)
- Bits 4-5: Pump selection (01=Pump1, 10=Pump2, 11=Pump3)
- Bit 6: Trigger input (rising edge with 50ms debounce)
- **INPUT_PULLUP logic**: Pins idle HIGH, trigger on LOW (inverted in software)

### Pump Mechanics
- **Step Resolution**: 0.04 mm/step
- **Volume per mm**: 0.20 mL/mm (configurable for calibration)
- **Discrete Volume**: 8.0 µL/step
- **Maximum Travel**: 40.0 mm per pump

## Installation

### System Dependencies
```bash
# Install pigpio daemon and Python library
sudo apt update
sudo apt install python3-pigpio
# Enable and start pigpio daemon
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```
### Python Environment

```bash
cd ~/Documents/syringe_pump_3ch_python/GPIO_GRBL
python3 -m venv ../syringe_pump_venv
source ../syringe_pump_venv/bin/activate
pip install pyserial pigpio
```

#### Usage
Starting the Application
```bash
cd ~/Documents/syringe_pump_3ch_python/GPIO_GRBL
source ../syringe_pump_venv/bin/activate
python syringe_pump_3ch_GPIO_GRBL.py
```
### Connecting Hardware
1. Connect GRBL Controller
Select USB serial port from dropdown (typically /dev/ttyUSB0 or /dev/ttyACM0)
Choose baud rate: 115200 (default)
Click "Connect GRBL"
Wait for "GRBL: Connected" status (green)
2. Connect GPIO Pins
Ensure pigpiod daemon is running: sudo systemctl status pigpiod
Click "Connect GPIO"
Status shows "GPIO: Connected" (green)
Trigger pin (GPIO 25) now actively monitored
#### Using Simulation Mode
Perfect for testing without physical triggers:

1. Click "Simulate Input: ON"
2. Random triggers generated every 2 seconds
3. Activity log shows GRBL commands: G90 G0 X12.500
4. Pump statistics update in real-time
5. Click "Simulate Input: OFF" to stop
#### Setting Desired Volumes
- Enter desired volume (µL) in "Desired µL" column
- Press Enter to update
- "Delivered µL" shows actual volume (rounded to 8µL increments)
- Example: 100µL desired → 104µL delivered (13 steps × 8µL)
#### Manual Position Control
- Click "Set Position" next to any pump
- Enter position (0-40 mm)
- Sends immediate GRBL command: G90 G0 [AXIS][POSITION]
- Useful for:
-- Initial synchronization with physical plunger
-- Recovery after power loss
-- Testing specific positions
#### Homing (Optional)
- **Requires endstop switches installed on each axis. DO NOT USE IF ENDSTOP SWITCHES NOT INSTALLED**
- Click "Home All" to run $H homing cycle
- All pumps move to limit switches, then zero positions
- Provides consistent reference point
#### Exporting Data
- Click "Export CSV" to save statistics
- Format: pump_stats_YYYYMMDD_HHMMSS.csv
- Includes: Triggers, Units, Desired/Delivered/Total volumes, Avg Response Time
### File Structure
```bash
~/Documents/syringe_pump_3ch_python/GPIO_GRBL/
├── syringe_pump_3ch_GPIO_GRBL.py    # Main application
├── pump_state_pi.json                # Persistent state
└── PumpMonitorLogs/                  # Auto-created
    ├── pump_log_YYYYMMDD_HHMMSS.txt
    └── pump_stats_YYYYMMDD_HHMMSS.csv
```
### GRBL Commands
#### Movement Commands (Absolute Mode)
```gcode
G90          ; Set absolute positioning mode
G0 X15.500   ; Move Pump 1 to 15.5mm
G0 Y23.250   ; Move Pump 2 to 23.25mm
G0 Z8.000    ; Move Pump 3 to 8.0mm
```
#### Status Query
```gcode
?            ; Request real-time status
; Response: <Idle|MPos:15.500,23.250,8.000|FS:0,0>
```
#### Homing (requires endstops)
```gcode
$H           ; Home all axes
#### Auto-Reversal Logic
The system automatically reverses pump direction when limits are reached:

#### Forward Limit Exceeded
```vbnet
Position: 38.0mm (Forward)
Trigger: 1600µL → 8.0mm movement
Check: 38.0 + 8.0 = 46.0 > 40.0 ❌
Action: Switch to Reverse, move to 40.0 - 8.0 = 32.0mm
Result: Full 1600µL dispensed ✓
```
#### Reverse Limit Exceeded
```vbnet
Position: 3.0mm (Reverse)
Trigger: 1200µL → 6.0mm movement
Check: 3.0 - 6.0 = -3.0 < 0 ❌
Action: Switch to Forward, move to 0 + 6.0 = 6.0mm
Result: Full 1200µL dispensed ✓
```
**Key Feature**: Full volume always dispensed, even when direction reverses mid-operation.

#### Statistics Display
##### Per-Pump Metrics
-**Triggers**: Total activation count
-**Total Units**: Cumulative magnitude sum
-**Desired µL**: User-specified volume per unit
-**Delivered µL**: Actual volume per unit (8µL increments)
-**Total µL**: Cumulative volume dispensed
-**Last Response**: Trigger-to-command delay (milliseconds)
##### Color Coding
Pump 1 (X): Blue
Pump 2 (Y): Green
Pump 3 (Z): Purple
Activity Log Tags
Blue (trigger): Pump activation events
Orange (grbl): GRBL commands and responses
Green (system): Connection, state changes
Purple (position): Manual position updates, auto-reversals
Red (error): Invalid encodings, communication failures
#### Response Time Analysis
Typical trigger-to-motion delays:

Ideal Conditions (System Idle)
```yaml
GPIO interrupt:    <1ms
Software debounce: 50ms
Serial transmit:   ~1ms (115200 baud)
GRBL parsing:      5-20ms
Motor start:       5-10ms
─────────────────────────
Total: ~80-100ms (consistent)
```
#### Busy System (GRBL buffer full)
- Delay increases to 100-300ms
- Not typical at 2-second intervals
- Monitored via "Last Response" column
#### Troubleshooting
##### GPIO Connection Fails
```bash
# Check pigpiod daemon status
sudo systemctl status pigpiod

# Restart if needed
sudo systemctl restart pigpiod

# Check for permission issues
sudo usermod -a -G gpio $USER
# Log out and back in for group change
```
##### GRBL Not Found
```bash
# List USB devices
ls /dev/ttyUSB* /dev/ttyACM*

# Check permissions
sudo usermod -a -G dialout $USER
# Log out and back in

# Test connection manually
sudo apt install screen
screen /dev/ttyUSB0 115200
# Type ? and press Enter (should see GRBL status)
# Exit: Ctrl+A then K
```
##### Invalid Pump Readings
Verify GPIO wiring matches BCM pin assignments
Check INPUT_PULLUP logic (idle=HIGH, trigger=LOW)
Use simulation mode to verify decoding logic
Monitor activity log for "Invalid pump encoding" errors
##### Position Drift
GRBL loses position on power cycle (unless homing enabled)
Use "Set Position" to resynchronize with physical plunger
Install endstops for reliable homing reference
##### Response Time Warnings
If delays exceed 150ms consistently:

Check Pi CPU usage: top
Verify GRBL buffer not congested: Send ? manually
Reduce trigger frequency if needed
Consider increasing baud rate to 230400 (requires GRBL recompilation)
#### Advanced Configuration
##### Calibration (Future Feature)
Planned calibration utility will allow:

Jog pumps forward/backward by set distances
Measure actual dispensed volume
Calculate real mL/mm ratio per pump
Save per-pump calibration factors
##### Current Calibration Method
Send known distance via "Set Position" (e.g., 10.0mm)
Measure dispensed volume with graduated cylinder
Calculate: actual_mL_per_mm = measured_mL / 10.0
Update self.ML_PER_MM in script
GRBL Settings
Check current settings via serial terminal:

```gcode
$$           ; View all settings

Key settings:
\$100=X steps/mm  (default: 250)
\$101=Y steps/mm
\$102=Z steps/mm
\$110=X max rate (mm/min)
\$120=X acceleration (mm/s²)
Adjust steps/mm for your stepper/leadscrew combination:
```
```
gcode
\$100=500     ; Set X-axis to 500 steps/mm
```
#### Parity Constraint (Simulation)
Critical: Bit index 3 shared between pump encoding and magnitude encoding.

##### Constraint Rules
```scss
Pump 1 (01) → bit[3]=1 → Requires EVEN magnitude (2,4,6,8,10,12,14,16)
Pump 2 (10) → bit[3]=0 → Requires ODD magnitude (1,3,5,7,9,11,13,15)
Pump 3 (11) → bit[3]=1 → Requires EVEN magnitude (2,4,6,8,10,12,14,16)
```
Simulation mode automatically adjusts random magnitudes ±1 to satisfy constraint.

##### System Requirements
Minimum
Raspberry Pi 3B+ or newer
1GB RAM
Raspbian Buster or newer
Python 3.7+
Recommended
Raspberry Pi 4 Model B (4GB+)
Raspberry Pi OS Bookworm (64-bit)
Python 3.11+
Dedicated 5V/3A power supply
##### Optional Hardware
7" touchscreen (uses GPIO 2/3 for I2C - compatible with this pin layout)
Endstop switches for homing (normally-open, connected to GRBL)
Emergency stop button (wired to GRBL reset pin)
##### Performance Notes
GPIO interrupt latency: <1ms (hardware-timed via pigpio)
Status polling overhead: ~5% CPU at 500ms intervals
GUI responsiveness: Smooth on Pi 4, acceptable on Pi 3B+
Maximum trigger rate: Tested reliable at 2Hz (500ms intervals)
##### Safety Considerations
No position feedback loop: System trusts GRBL reported positions
Endstops recommended: Prevents mechanical damage at limits
Emergency stop: Wire physical E-stop to GRBL reset pin
Power loss: Positions lost unless homing enabled
Volume accuracy: Depends on mechanical calibration
#### Future Enhancements
 Calibration wizard GUI
 GRBL error parsing and recovery
 Multi-axis simultaneous movement testing
 Real-time volume delivery graph
 Email/SMS alerts for errors
 Systemd auto-start service
 Remote monitoring via web interface
#### License
MIT License - Free to modify and distribute

##### Author
eee@jhu.edu

Developed for the Stuphorn Lab precision syringe pump control in laboratory automation applications.

### Support
For issues specific to:

GRBL: https://github.com/gnea/grbl/wiki
pigpio: http://abyz.me.uk/rpi/pigpio/
Raspberry Pi GPIO: https://pinout.xyz/
Version: 1.0.0 (Raspberry Pi GPIO + GRBL)

Last Updated: 2024

```sql
This README covers everything from installation to troubleshooting, with specific examples fo
