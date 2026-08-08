# syringe_pump_3ch_GPIO_GRBL.py

# syringe_pump_3ch_GPIO_GRBL.py

#!/usr/bin/env python3
"""
Raspberry Pi Syringe Pump Monitor with GRBL Control
Reads GPIO pins for trigger signals and controls 3 pumps via GRBL
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import pigpio
import threading
import time
import json
import os
from datetime import datetime
from pathlib import Path

class PumpMonitorPi:
    def __init__(self, root):
        self.root = root
        self.root.title("Pump Monitor - Raspberry Pi")
        self.root.geometry("1100x950")
        
        # GPIO Pin Configuration (BCM numbering)
        self.GPIO_PINS = {
            'bit0': 17,  # Magnitude LSB
            'bit1': 18,
            'bit2': 27,
            'bit3': 22,  # Magnitude MSB / Pump bit overlap
            'bit4': 23,  # Pump bit
            'bit5': 24,  # Pump bit
            'bit6': 25,  # Trigger input
        }
        
        # Pump mechanics
        self.MM_PER_STEP = 0.04
        self.ML_PER_MM = 0.20
        self.UL_PER_STEP = 8.0
        self.MAX_TRAVEL_MM = 40.0
        
        # GRBL axis mapping
        self.PUMP_AXIS = {1: 'X', 2: 'Y', 3: 'Z'}
        
        # Serial connection
        self.grbl_serial = None
        self.grbl_connected = False
        
        # GPIO connection
        self.pi_gpio = None
        self.gpio_connected = False
        self.last_trigger_time = 0
        self.debounce_ms = 50
        
        # Statistics
        self.pump_stats = {}
        self.pump_positions = {}
        self.pump_directions = {}
        self.trigger_count = 0
        
        for pump_num in [1, 2, 3]:
            self.pump_stats[pump_num] = {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.DoubleVar(value=100.0),
                "delivered_unit_size": tk.StringVar(value="104.0"),
                "total_delivered": tk.StringVar(value="0.0"),
                "last_response_ms": 0,
                "avg_response_ms": 0,
                "response_times": []
            }
            self.pump_positions[pump_num] = 0.0
            self.pump_directions[pump_num] = "Forward"
        
        # Simulation
        self.simulation_enabled = False
        self.simulation_timer = None
        
        # State file
        self.state_file = Path(__file__).parent / "pump_state_pi.json"
        
        # Log directory
        self.log_dir = Path(__file__).parent / "PumpMonitorLogs"
        self.log_dir.mkdir(exist_ok=True)
        
        # Activity log storage
        self.activity_log = []
        
        # GRBL status polling
        self.status_poll_timer = None
        self.grbl_status_lock = threading.Lock()
        self.grbl_positions = {'X': 0.0, 'Y': 0.0, 'Z': 0.0}
        self.grbl_state = "Idle"
        
        self.create_widgets()
        self.load_state()
        
        # Fix initial focus
        self.root.after(100, self.fix_initial_focus)
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def fix_initial_focus(self):
        """Ensure window gets proper focus on launch"""
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        
        import platform
        system = platform.system()
        
        if system == 'Linux':
            try:
                self.root.attributes('-topmost', True)
                self.root.after(100, lambda: self.root.attributes('-topmost', False))
            except:
                pass
        
        self.root.after(150, lambda: self.port_combo.focus_set())
    
    def create_widgets(self):
        # Connection frame
        conn_frame = ttk.LabelFrame(self.root, text="GRBL Connection", padding=10)
        conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, sticky=tk.W)
        self.port_combo = ttk.Combobox(conn_frame, width=15)
        self.port_combo.grid(row=0, column=1, padx=5)
        self.refresh_ports()
        
        ttk.Button(conn_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=5)
        
        ttk.Label(conn_frame, text="Baud:").grid(row=0, column=3, sticky=tk.W, padx=(20,0))
        self.baud_combo = ttk.Combobox(conn_frame, width=10, values=["9600", "115200"])
        self.baud_combo.set("115200")
        self.baud_combo.grid(row=0, column=4, padx=5)
        
        self.connect_btn = ttk.Button(conn_frame, text="Connect GRBL", command=self.toggle_grbl_connection)
        self.connect_btn.grid(row=0, column=5, padx=5)
        
        self.grbl_status_label = ttk.Label(conn_frame, text="GRBL: Disconnected", foreground="red")
        self.grbl_status_label.grid(row=0, column=6, padx=10)
        
        # GPIO connection
        ttk.Label(conn_frame, text="GPIO:").grid(row=1, column=0, sticky=tk.W)
        self.gpio_connect_btn = ttk.Button(conn_frame, text="Connect GPIO", command=self.toggle_gpio_connection)
        self.gpio_connect_btn.grid(row=1, column=1, padx=5)
        
        self.gpio_status_label = ttk.Label(conn_frame, text="GPIO: Disconnected", foreground="red")
        self.gpio_status_label.grid(row=1, column=2, padx=10)
        
        # Simulation toggle
        self.simulate_btn = ttk.Button(conn_frame, text="Simulate Input: OFF", command=self.toggle_simulation)
        self.simulate_btn.grid(row=1, column=5, padx=5)
        
        # Pin display frame
        pin_frame = ttk.LabelFrame(self.root, text="Trigger Status", padding=10)
        pin_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Label(pin_frame, text="Binary Code:").grid(row=0, column=0, sticky=tk.W)
        self.binary_label = ttk.Label(pin_frame, text="0000000", font=("Courier", 12, "bold"))
        self.binary_label.grid(row=0, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(pin_frame, text="Magnitude:").grid(row=1, column=0, sticky=tk.W)
        self.magnitude_label = ttk.Label(pin_frame, text="0", font=("Arial", 12))
        self.magnitude_label.grid(row=1, column=1, sticky=tk.W, padx=10)
        
        ttk.Label(pin_frame, text="Active Pump:").grid(row=2, column=0, sticky=tk.W)
        self.pump_label = ttk.Label(pin_frame, text="None", font=("Arial", 12, "bold"))
        self.pump_label.grid(row=2, column=1, sticky=tk.W, padx=10)
        
        # Trigger LED and counter
        ttk.Label(pin_frame, text="Trigger LED:").grid(row=0, column=2, sticky=tk.W, padx=(30,0))
        self.led_canvas = tk.Canvas(pin_frame, width=30, height=30)
        self.led_canvas.grid(row=0, column=3, padx=5)
        self.led_indicator = self.led_canvas.create_oval(5, 5, 25, 25, fill="red", outline="darkred")
        
        ttk.Label(pin_frame, text="Total Triggers:").grid(row=1, column=2, sticky=tk.W, padx=(30,0))
        self.trigger_count_label = ttk.Label(pin_frame, text="0", font=("Arial", 12, "bold"))
        self.trigger_count_label.grid(row=1, column=3, sticky=tk.W, padx=5)
        
        # GRBL Status
        ttk.Label(pin_frame, text="GRBL State:").grid(row=2, column=2, sticky=tk.W, padx=(30,0))
        self.grbl_state_label = ttk.Label(pin_frame, text="Idle", font=("Arial", 12))
        self.grbl_state_label.grid(row=2, column=3, sticky=tk.W, padx=5)
        
        # Statistics frame
        stats_frame = ttk.LabelFrame(self.root, text="Pump Statistics", padding=10)
        stats_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        headers = ["Pump", "Triggers", "Total Units", "Desired µL", "Delivered µL", "Total µL", "Last Response"]
        for col, header in enumerate(headers):
            ttk.Label(stats_frame, text=header, font=("Arial", 10, "bold")).grid(row=0, column=col, padx=5, pady=5)
        
        self.stats_labels = {}
        for i, pump_num in enumerate([1, 2, 3], start=1):
            pump_color = {1: "blue", 2: "green", 3: "purple"}[pump_num]
            
            ttk.Label(stats_frame, text=f"Pump {pump_num}", foreground=pump_color, font=("Arial", 10, "bold")).grid(row=i, column=0, padx=5, pady=2)
            
            triggers_label = ttk.Label(stats_frame, text="0")
            triggers_label.grid(row=i, column=1, padx=5, pady=2)
            
            units_label = ttk.Label(stats_frame, text="0")
            units_label.grid(row=i, column=2, padx=5, pady=2)
            
            desired_entry = ttk.Entry(stats_frame, textvariable=self.pump_stats[pump_num]["desired_unit_size"], width=10)
            desired_entry.grid(row=i, column=3, padx=5, pady=2)
            desired_entry.bind('<Return>', lambda e, p=pump_num: self.update_desired_size(p))
            desired_entry.bind('<FocusIn>', lambda e: e.widget.select_range(0, tk.END))
            
            delivered_label = ttk.Label(stats_frame, textvariable=self.pump_stats[pump_num]["delivered_unit_size"])
            delivered_label.grid(row=i, column=4, padx=5, pady=2)
            
            total_label = ttk.Label(stats_frame, textvariable=self.pump_stats[pump_num]["total_delivered"])
            total_label.grid(row=i, column=5, padx=5, pady=2)
            
            response_label = ttk.Label(stats_frame, text="- ms")
            response_label.grid(row=i, column=6, padx=5, pady=2)
            
            self.stats_labels[pump_num] = {
                "triggers": triggers_label,
                "units": units_label,
                "response": response_label
            }
        
        # Position frame
        position_frame = ttk.LabelFrame(self.root, text="Plunger Positions", padding=10)
        position_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        self.position_labels = {}
        self.position_bars = {}
        
        for i, pump_num in enumerate([1, 2, 3]):
            pump_color = {1: "blue", 2: "green", 3: "purple"}[pump_num]
            axis = self.PUMP_AXIS[pump_num]
            
            ttk.Label(position_frame, text=f"Pump {pump_num} ({axis}):", foreground=pump_color, font=("Arial", 10, "bold")).grid(row=i, column=0, sticky=tk.W, padx=5, pady=5)
            
            pos_label = ttk.Label(position_frame, text="0.00 mm (Forward)", font=("Arial", 9))
            pos_label.grid(row=i, column=1, sticky=tk.W, padx=10)
            self.position_labels[pump_num] = pos_label
            
            progress = ttk.Progressbar(position_frame, length=300, mode='determinate', maximum=self.MAX_TRAVEL_MM)
            progress.grid(row=i, column=2, padx=10)
            self.position_bars[pump_num] = progress
            
            ttk.Button(position_frame, text="Set Position", command=lambda p=pump_num: self.set_position_dialog(p)).grid(row=i, column=3, padx=5)
        
        self.update_position_displays()
        
        # Control buttons frame
        button_frame = ttk.Frame(self.root)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Home All", command=self.home_all_pumps).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Reset Stats", command=self.reset_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Calibration", command=self.open_calibration).pack(side=tk.LEFT, padx=5)
        
        # Activity log
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=110, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags
        self.log_text.tag_config("trigger", foreground="blue")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("system", foreground="green")
        self.log_text.tag_config("position", foreground="purple")
        self.log_text.tag_config("grbl", foreground="orange")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(5, weight=1)
    
    def refresh_ports(self):
        """Refresh available serial ports"""
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.port_combo['values'] = port_list
        if port_list:
            self.port_combo.set(port_list[0])
    
    def toggle_grbl_connection(self):
        """Connect/disconnect to GRBL controller"""
        if not self.grbl_connected:
            try:
                port = self.port_combo.get()
                baud = int(self.baud_combo.get())
                
                self.grbl_serial = serial.Serial(port, baud, timeout=0.1, write_timeout=0.1)
                time.sleep(2)  # Wait for GRBL initialization
                
                # Wake up GRBL
                self.grbl_serial.write(b"\r\n\r\n")
                time.sleep(1)
                self.grbl_serial.flushInput()
                
                self.grbl_connected = True
                self.connect_btn.config(text="Disconnect GRBL")
                self.grbl_status_label.config(text="GRBL: Connected", foreground="green")
                
                # Start status polling
                self.start_grbl_polling()
                
                self.log_message("GRBL controller connected", "system")
                
            except Exception as e:
                messagebox.showerror("Connection Error", f"Failed to connect to GRBL:\n{e}")
        else:
            self.disconnect_grbl()
    
    def disconnect_grbl(self):
        """Disconnect from GRBL"""
        if self.grbl_serial:
            self.stop_grbl_polling()
            self.grbl_serial.close()
            self.grbl_serial = None
        
        self.grbl_connected = False
        self.connect_btn.config(text="Connect GRBL")
        self.grbl_status_label.config(text="GRBL: Disconnected", foreground="red")
        self.log_message("GRBL controller disconnected", "system")
    
    def toggle_gpio_connection(self):
        """Connect/disconnect GPIO pins"""
        if not self.gpio_connected:
            try:
                self.pi_gpio = pigpio.pi()
                if not self.pi_gpio.connected:
                    raise Exception("pigpiod daemon not running. Run: sudo systemctl start pigpiod")
                
                # Configure all pins as inputs with pull-up
                for pin_name, pin_num in self.GPIO_PINS.items():
                    self.pi_gpio.set_mode(pin_num, pigpio.INPUT)
                    self.pi_gpio.set_pull_up_down(pin_num, pigpio.PUD_UP)
                
                # Set up interrupt on trigger pin (bit6)
                self.pi_gpio.set_glitch_filter(self.GPIO_PINS['bit6'], 10000)  # 10ms glitch filter
                self.pi_gpio.callback(self.GPIO_PINS['bit6'], pigpio.RISING_EDGE, self.gpio_trigger_callback)
                
                self.gpio_connected = True
                self.gpio_connect_btn.config(text="Disconnect GPIO")
                self.gpio_status_label.config(text="GPIO: Connected", foreground="green")
                self.log_message("GPIO pins connected and configured", "system")
                
            except Exception as e:
                messagebox.showerror("GPIO Error", f"Failed to initialize GPIO:\n{e}\n\nEnsure pigpiod is running:\nsudo systemctl start pigpiod")
        else:
            self.disconnect_gpio()
    
    def disconnect_gpio(self):
        """Disconnect GPIO"""
        if self.pi_gpio:
            self.pi_gpio.stop()
            self.pi_gpio = None
        
        self.gpio_connected = False
        self.gpio_connect_btn.config(text="Connect GPIO")
        self.gpio_status_label.config(text="GPIO: Disconnected", foreground="red")
        self.log_message("GPIO disconnected", "system")
    
    def gpio_trigger_callback(self, gpio_pin, level, tick):
        """Callback for GPIO trigger interrupt"""
        current_time = time.time() * 1000  # Convert to ms
        
        # Software debounce
        if current_time - self.last_trigger_time < self.debounce_ms:
            return
        
        self.last_trigger_time = current_time
        
        # Read all GPIO pins
        bit_string = self.read_gpio_pins()
        
        # Process in main thread
        self.root.after(0, lambda: self.process_trigger(bit_string, current_time))
    
    def read_gpio_pins(self):
        """Read all 7 GPIO pins and return bit string"""
        if not self.pi_gpio:
            return "0000000"
        
        bits = []
        for i in range(7):
            pin_key = f'bit{i}'
            if pin_key in self.GPIO_PINS:
                # Read pin (inverted because INPUT_PULLUP - pressed = LOW)
                value = 1 - self.pi_gpio.read(self.GPIO_PINS[pin_key])
                bits.append(str(value))
            else:
                bits.append('0')
        
        return ''.join(bits)
    
    def process_trigger(self, bit_string, trigger_time_ms):
        """Process trigger event"""
        # Flash LED
        self.flash_trigger_led()
        
        # Update trigger count
        self.trigger_count += 1
        self.trigger_count_label.config(text=str(self.trigger_count))
        
        # Update display
        self.binary_label.config(text=bit_string)
        
        # Decode magnitude (bits 6,5,4,3)
        mag_bits = bit_string[6] + bit_string[5] + bit_string[4] + bit_string[3]
        magnitude = int(mag_bits, 2) + 1  # 0-15 → 1-16
        
        # Decode pump (bits 2,3)
        pump_bits = bit_string[2:4]
        pump_map = {'01': 1, '10': 2, '11': 3, '00': None}
        pump_num = pump_map.get(pump_bits)
        
        self.magnitude_label.config(text=str(magnitude))
        
        if pump_num:
            pump_color = {1: "blue", 2: "green", 3: "purple"}[pump_num]
            self.pump_label.config(text=f"Pump {pump_num}", foreground=pump_color)
            
            # Update statistics
            self.pump_stats[pump_num]["triggers"] += 1
            self.pump_stats[pump_num]["total_units"] += magnitude
            
            self.stats_labels[pump_num]["triggers"].config(text=str(self.pump_stats[pump_num]["triggers"]))
            self.stats_labels[pump_num]["units"].config(text=str(self.pump_stats[pump_num]["total_units"]))
            
            # Calculate volumes
            desired_ul = self.pump_stats[pump_num]["desired_unit_size"].get() * magnitude
            delivered_ul = self.calculate_discrete_volume(desired_ul)
            
            # Update total
            current_total = float(self.pump_stats[pump_num]["total_delivered"].get())
            new_total = current_total + delivered_ul
            self.pump_stats[pump_num]["total_delivered"].set(f"{new_total:.1f}")
            
            # Send GRBL command
            self.send_pump_command(pump_num, delivered_ul, trigger_time_ms)
            
            # Log activity
            self.log_message(f"Trigger: Pump {pump_num}, Magnitude {magnitude}, Delivered {delivered_ul:.1f} uL", "trigger")
            
        else:
            self.pump_label.config(text="Invalid (00)", foreground="red")
            self.log_message(f"Invalid pump encoding: {pump_bits}", "error")
    
    def send_pump_command(self, pump_num, volume_ul, trigger_time_ms):
        """Send GRBL movement command for pump"""
        # Calculate distance
        distance_mm = volume_ul / 1000.0 / self.ML_PER_MM
        
        # Get current position and direction
        current_pos = self.pump_positions[pump_num]
        direction = self.pump_directions[pump_num]
        
        # Calculate new position
        if direction == "Forward":
            new_pos = current_pos + distance_mm
            if new_pos > self.MAX_TRAVEL_MM:
                # Reverse direction and dispense full amount
                self.pump_directions[pump_num] = "Reverse"
                new_pos = self.MAX_TRAVEL_MM - distance_mm
                self.log_message(f"Pump {pump_num} would exceed limit, reversed to {new_pos:.2f}mm", "position")
        else:  # Reverse
            new_pos = current_pos - distance_mm
            if new_pos < 0:
                # Forward direction and dispense full amount
                self.pump_directions[pump_num] = "Forward"
                new_pos = 0 + distance_mm
                self.log_message(f"Pump {pump_num} would go below zero, forward to {new_pos:.2f}mm", "position")
        
        # Update position
        self.pump_positions[pump_num] = new_pos
        
        # Build GRBL command
        axis = self.PUMP_AXIS[pump_num]
        command = f"G90 G0 {axis}{new_pos:.3f}\n"
        
        if not self.grbl_connected:
            # Simulation mode - log command but don't send
            self.log_message(f"GRBL Command (simulation): {command.strip()}", "grbl")
            self.update_position_displays()
            self.save_state()
            return
        
        try:
            # Send command
            self.grbl_serial.write(command.encode())
            
            # Calculate response time
            response_time_ms = (time.time() * 1000) - trigger_time_ms
            
            # Update response time stats
            self.pump_stats[pump_num]["last_response_ms"] = response_time_ms
            self.pump_stats[pump_num]["response_times"].append(response_time_ms)
            
            # Keep only last 20 response times for average
            if len(self.pump_stats[pump_num]["response_times"]) > 20:
                self.pump_stats[pump_num]["response_times"].pop(0)
            
            avg_response = sum(self.pump_stats[pump_num]["response_times"]) / len(self.pump_stats[pump_num]["response_times"])
            self.pump_stats[pump_num]["avg_response_ms"] = avg_response
            
            # Update display
            self.stats_labels[pump_num]["response"].config(text=f"{int(response_time_ms)} ms")
            
            self.log_message(f"GRBL Command sent: {command.strip()} | Response: {int(response_time_ms)}ms", "grbl")
            
        except Exception as e:
            self.log_message(f"GRBL command failed: {e}", "error")
        
        self.update_position_displays()
        self.save_state()
    
    def start_grbl_polling(self):
        """Start polling GRBL status"""
        if self.grbl_connected:
            self.poll_grbl_status()
    
    def stop_grbl_polling(self):
        """Stop polling GRBL status"""
        if self.status_poll_timer:
            self.root.after_cancel(self.status_poll_timer)
            self.status_poll_timer = None
    
    def poll_grbl_status(self):
        """Query GRBL status"""
        if not self.grbl_connected:
            return
        
        try:
            # Send status query
            self.grbl_serial.write(b'?')
            
            # Read response (non-blocking)
            response = self.grbl_serial.readline().decode('utf-8', errors='ignore').strip()
            
            if response.startswith('<') and response.endswith('>'):
                self.parse_grbl_status(response)
            
        except Exception as e:
            pass  # Silently fail on status query errors
        
        # Schedule next poll
        self.status_poll_timer = self.root.after(500, self.poll_grbl_status)
    
    def parse_grbl_status(self, status_string):
        """Parse GRBL status response"""
        # Example: <Idle|MPos:10.000,20.000,5.000|FS:0,0>
        try:
            parts = status_string[1:-1].split('|')
            
            # Extract state
            state = parts[0]
            with self.grbl_status_lock:
                self.grbl_state = state
            self.grbl_state_label.config(text=state)
            
            # Extract positions
            for part in parts:
                if part.startswith('MPos:') or part.startswith('WPos:'):
                    pos_str = part.split(':')[1]
                    positions = pos_str.split(',')
                    
                    with self.grbl_status_lock:
                        if len(positions) >= 3:
                            self.grbl_positions['X'] = float(positions[0])
                            self.grbl_positions['Y'] = float(positions[1])
                            self.grbl_positions['Z'] = float(positions[2])
                    
                    # Update pump positions from GRBL feedback
                    for pump_num in [1, 2, 3]:
                        axis = self.PUMP_AXIS[pump_num]
                        grbl_pos = self.grbl_positions[axis]
                        # Only update if significantly different (avoid jitter)
                        if abs(self.pump_positions[pump_num] - grbl_pos) > 0.1:
                            self.pump_positions[pump_num] = grbl_pos
                            self.update_position_displays()
        
        except Exception as e:
            pass  # Silently fail on parse errors
    
    def home_all_pumps(self):
        """Send homing command to GRBL"""
        if not self.grbl_connected:
            messagebox.showwarning("Not Connected", "GRBL not connected")
            return
        
        result = messagebox.askyesno("Home All Axes", 
                                      "This will home all pumps to their limit switches.\n\n"
                                      "Ensure endstops are properly installed.\n\n"
                                      "Continue?")
        if result:
            try:
                self.grbl_serial.write(b'$H\n')
                self.log_message("Homing cycle started", "grbl")
                
                # Reset positions after homing
                for pump_num in [1, 2, 3]:
                    self.pump_positions[pump_num] = 0.0
                    self.pump_directions[pump_num] = "Forward"
                
                self.update_position_displays()
                self.save_state()
                
            except Exception as e:
                messagebox.showerror("Homing Error", f"Failed to home: {e}")
    
    def calculate_discrete_volume(self, desired_ul):
        """Calculate actual deliverable volume in discrete steps"""
        steps_needed = desired_ul / self.UL_PER_STEP
        steps_actual = int(steps_needed) if steps_needed == int(steps_needed) else int(steps_needed) + 1
        return round(steps_actual * self.UL_PER_STEP, 3)
    
    def update_desired_size(self, pump_num):
        """Update desired unit size and recalculate delivered size"""
        try:
            desired = self.pump_stats[pump_num]["desired_unit_size"].get()
            delivered = self.calculate_discrete_volume(desired)
            self.pump_stats[pump_num]["delivered_unit_size"].set(f"{delivered:.1f}")
            self.log_message(f"Pump {pump_num} desired size updated: {desired:.1f} uL -> {delivered:.1f} uL delivered", "system")
            self.save_state()
        except:
            pass
    
    def update_position_displays(self):
        """Update position labels and progress bars"""
        for pump_num in [1, 2, 3]:
            position = self.pump_positions[pump_num]
            direction = self.pump_directions[pump_num]
            
            self.position_labels[pump_num].config(text=f"{position:.2f} mm ({direction})")
            self.position_bars[pump_num]['value'] = position
    
    def set_position_dialog(self, pump_num):
        """Open dialog to manually set pump position"""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Set Pump {pump_num} Position")
        dialog.geometry("300x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text=f"Enter position for Pump {pump_num} (0-{self.MAX_TRAVEL_MM} mm):", 
                 padding=10).pack()
        
        pos_var = tk.DoubleVar(value=self.pump_positions[pump_num])
        pos_entry = ttk.Entry(dialog, textvariable=pos_var, width=15)
        pos_entry.pack(pady=10)
        pos_entry.focus_set()
        pos_entry.select_range(0, tk.END)
        
        def apply_position():
            try:
                new_pos = pos_var.get()
                if 0 <= new_pos <= self.MAX_TRAVEL_MM:
                    self.pump_positions[pump_num] = new_pos
                    
                    # Send GRBL position update
                    if self.grbl_connected:
                        axis = self.PUMP_AXIS[pump_num]
                        command = f"G90 G0 {axis}{new_pos:.3f}\n"
                        self.grbl_serial.write(command.encode())
                        self.log_message(f"Position set: Pump {pump_num} -> {new_pos:.2f} mm", "position")
                    
                    self.update_position_displays()
                    self.save_state()
                    dialog.destroy()
                else:
                    messagebox.showerror("Invalid Position", 
                                       f"Position must be between 0 and {self.MAX_TRAVEL_MM} mm")
            except:
                messagebox.showerror("Invalid Input", "Please enter a valid number")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Apply", command=apply_position).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        pos_entry.bind('<Return>', lambda e: apply_position())
    
    def toggle_simulation(self):
        """Toggle simulation mode"""
        self.simulation_enabled = not self.simulation_enabled
        
        if self.simulation_enabled:
            self.simulate_btn.config(text="Simulate Input: ON")
            self.log_message("Simulation mode enabled", "system")
            self.schedule_simulation()
        else:
            self.simulate_btn.config(text="Simulate Input: OFF")
            self.log_message("Simulation mode disabled", "system")
            if self.simulation_timer:
                self.root.after_cancel(self.simulation_timer)
    
    def schedule_simulation(self):
        """Schedule next simulated trigger"""
        if self.simulation_enabled:
            self.generate_simulated_trigger()
            self.simulation_timer = self.root.after(2000, self.schedule_simulation)
    
    def generate_simulated_trigger(self):
        """Generate random trigger for testing"""
        import random
        
        # Random pump (1-3)
        pump = random.randint(1, 3)
        pump_encoding = {1: '01', 2: '10', 3: '11'}
        pump_bits = pump_encoding[pump]
        
        # Random magnitude (1-16)
        magnitude = random.randint(1, 16)
        
        # Apply parity constraint (index 3 shared between pump and magnitude)
        if pump_bits[1] == '1':  # Pump 1 or 3
            # Need mag_bits[3] = '1' → magnitude EVEN
            if magnitude % 2 == 1:
                magnitude = magnitude + 1 if magnitude < 16 else magnitude - 1
        else:  # Pump 2
            # Need mag_bits[3] = '0' → magnitude ODD
            if magnitude % 2 == 0:
                magnitude = magnitude + 1 if magnitude < 16 else magnitude - 1
        
        # Convert magnitude to 4-bit binary
        mag_value = magnitude - 1  # 1-16 → 0-15
        mag_bits = format(mag_value, '04b')
        
        # Construct bit string: [0][0][pump0][pump1][mag2][mag1][mag0]
        bit_string = '0' + '0' + pump_bits[0] + pump_bits[1] + mag_bits[2] + mag_bits[1] + mag_bits[0]
        
        # Process trigger
        trigger_time_ms = time.time() * 1000
        self.process_trigger(bit_string, trigger_time_ms)
    
    def flash_trigger_led(self):
        """Flash the trigger LED"""
        self.led_canvas.itemconfig(self.led_indicator, fill="green")
        self.root.after(200, lambda: self.led_canvas.itemconfig(self.led_indicator, fill="red"))
    
    def log_message(self, message, tag="system"):
        """Add message to activity log"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.activity_log.append(log_entry)
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_entry, tag)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
    
    def clear_log(self):
        """Clear the activity log"""
        result = messagebox.askyesno("Clear Log", "Clear activity log?")
        if result:
            self.activity_log.clear()
            self.log_text.config(state='normal')
            self.log_text.delete(1.0, tk.END)
            self.log_text.config(state='disabled')
            self.log_message("Activity log cleared", "system")
    
    def reset_stats(self):
        """Reset all statistics"""
        result = messagebox.askyesno("Reset Statistics", 
                                     "Reset all pump statistics?\n\nThis will NOT reset positions.")
        if result:
            for pump_num in [1, 2, 3]:
                self.pump_stats[pump_num]["triggers"] = 0
                self.pump_stats[pump_num]["total_units"] = 0
                self.pump_stats[pump_num]["total_delivered"].set("0.0")
                self.pump_stats[pump_num]["response_times"].clear()
                self.pump_stats[pump_num]["last_response_ms"] = 0
                self.pump_stats[pump_num]["avg_response_ms"] = 0
                
                self.stats_labels[pump_num]["triggers"].config(text="0")
                self.stats_labels[pump_num]["units"].config(text="0")
                self.stats_labels[pump_num]["response"].config(text="- ms")
            
            self.trigger_count = 0
            self.trigger_count_label.config(text="0")
            
            self.log_message("Statistics reset", "system")
            self.save_state()
    
    def export_csv(self):
        """Export statistics to CSV"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = self.log_dir / f"pump_stats_{timestamp}.csv"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("Pump,Triggers,Total Units,Desired uL,Delivered uL,Total uL,Avg Response ms\n")
                
                for pump_num in [1, 2, 3]:
                    triggers = self.pump_stats[pump_num]["triggers"]
                    units = self.pump_stats[pump_num]["total_units"]
                    desired = self.pump_stats[pump_num]["desired_unit_size"].get()
                    delivered = self.pump_stats[pump_num]["delivered_unit_size"].get()
                    total = self.pump_stats[pump_num]["total_delivered"].get()
                    avg_response = int(self.pump_stats[pump_num]["avg_response_ms"])
                    
                    f.write(f"{pump_num},{triggers},{units},{desired},{delivered},{total},{avg_response}\n")
            
            self.log_message(f"Statistics exported to {filename.name}", "system")
            messagebox.showinfo("Export Complete", f"Statistics saved to:\n{filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")
    
    def open_calibration(self):
        """Open calibration dialog"""
        messagebox.showinfo("Calibration", "Calibration utility coming soon!\n\n"
                           "Features:\n"
                           "- Jog pumps forward/backward\n"
                           "- Measure dispensed volume\n"
                           "- Calculate mL/mm ratio\n"
                           "- Delay measurement test")
    
    def save_state(self):
        """Save current state to JSON file"""
        state = {
            "positions": self.pump_positions,
            "directions": self.pump_directions,
            "stats": {}
        }
        
        for pump_num in [1, 2, 3]:
            state["stats"][pump_num] = {
                "triggers": self.pump_stats[pump_num]["triggers"],
                "total_units": self.pump_stats[pump_num]["total_units"],
                "desired_unit_size": self.pump_stats[pump_num]["desired_unit_size"].get(),
                "total_delivered": self.pump_stats[pump_num]["total_delivered"].get()
            }
        
        try:
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.log_message(f"Failed to save state: {e}", "error")
    
    def load_state(self):
        """Load state from JSON file"""
        if not self.state_file.exists():
            self.log_message("No previous state found - starting fresh", "system")
            return
        
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            # Restore positions
            if "positions" in state:
                for pump_num in [1, 2, 3]:
                    if str(pump_num) in state["positions"]:
                        self.pump_positions[pump_num] = state["positions"][str(pump_num)]
            
            if "directions" in state:
                for pump_num in [1, 2, 3]:
                    if str(pump_num) in state["directions"]:
                        self.pump_directions[pump_num] = state["directions"][str(pump_num)]
            
            # Restore stats
            if "stats" in state:
                for pump_num in [1, 2, 3]:
                    if str(pump_num) in state["stats"]:
                        pump_state = state["stats"][str(pump_num)]
                        self.pump_stats[pump_num]["triggers"] = pump_state.get("triggers", 0)
                        self.pump_stats[pump_num]["total_units"] = pump_state.get("total_units", 0)
                        self.pump_stats[pump_num]["desired_unit_size"].set(pump_state.get("desired_unit_size", 100.0))
                        self.pump_stats[pump_num]["total_delivered"].set(pump_state.get("total_delivered", "0.0"))
                        
                        # Update labels
                        self.stats_labels[pump_num]["triggers"].config(text=str(self.pump_stats[pump_num]["triggers"]))
                        self.stats_labels[pump_num]["units"].config(text=str(self.pump_stats[pump_num]["total_units"]))
                        
                        # Recalculate delivered size
                        self.update_desired_size(pump_num)
            
            self.update_position_displays()
            self.log_message("Previous state restored", "system")
            
        except Exception as e:
            self.log_message(f"Failed to load state: {e}", "error")
    
    def on_closing(self):
        """Handle window close event"""
        # Save activity log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = self.log_dir / f"pump_log_{timestamp}.txt"
        
        try:
            with open(log_filename, 'w', encoding='utf-8') as f:
                for entry in self.activity_log:
                    f.write(entry.replace('µ', 'u'))  # Convert µ for compatibility
        except:
            pass
        
        # Save state
        self.save_state()
        
        # Disconnect hardware
        if self.gpio_connected:
            self.disconnect_gpio()
        
        if self.grbl_connected:
            self.disconnect_grbl()
        
        # Stop simulation
        if self.simulation_timer:
            self.root.after_cancel(self.simulation_timer)
        
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PumpMonitorPi(root)
    root.mainloop()
