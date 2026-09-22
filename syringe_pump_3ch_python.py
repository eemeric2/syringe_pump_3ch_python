# syringe_pump_3ch_python.py

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime
import serial
import serial.tools.list_ports
import threading
import time
import json
import os
import csv

class PumpMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Arduino Pump Monitor")
        self.root.geometry("1000x900")
        
        # Constants
        self.MM_PER_STEP = 0.04
        self.ML_PER_MM = 0.20
        self.UL_PER_STEP = 8.0
        self.MAX_TRAVEL_MM = 40.0
        
        # Serial connection
        self.serial_connection = None
        self.reading_thread = None
        self.stop_reading = False
        self.connection_timestamp = None
        
        # Simulation
        self.simulation_enabled = False
        self.simulation_timer = None
        
        # Script directory for file paths
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Statistics storage
        self.pump_stats = {}
        self.desired_ul_history = {}  # track desired µL changes
        for pump_num in [1, 2, 3]:
            self.pump_stats[pump_num] = {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),
                "delivered_unit_size": tk.StringVar(value="0.0"),
                "total_delivered": tk.StringVar(value="0.0"),
                "position_mm": 0.0,
                "direction": 1
            }
        self.desired_ul_history[pump_num] = []  # ADD THIS - list of (timestamp, value) tuples
        self.total_triggers = 0
        
        
        # Fix initial focus issue
        self.root.after(100, self.fix_initial_focus)
        
        # Load saved state
        self.load_state()
        # Ensure all pumps have history initialized
        for pump_num in [1, 2, 3]:
            if not self.desired_ul_history[pump_num]:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                desired = float(self.pump_stats[pump_num]["desired_unit_size"].get())
                self.desired_ul_history[pump_num] = [(timestamp, desired)]

        # Build GUI
        self.create_widgets()
        
        # Fix initial focus issue
        self.root.after(100, self.fix_initial_focus)
    
        # Trigger LED state
        self.led_active = False
        
        # Protocol for window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        # Connection frame
        conn_frame = ttk.LabelFrame(self.root, text="Serial Connection", padding=10)
        conn_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, sticky=tk.W)
        self.port_combo = ttk.Combobox(conn_frame, width=15)
        self.port_combo.grid(row=0, column=1, padx=5)
        self.refresh_ports()
        
        ttk.Button(conn_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=5)
        
        ttk.Label(conn_frame, text="Baud:").grid(row=0, column=3, sticky=tk.W, padx=(20,0))
        self.baud_combo = ttk.Combobox(conn_frame, width=10, values=["115200"])
        self.baud_combo.set("115200")
        self.baud_combo.grid(row=0, column=4, padx=5)
        
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5)
        
        self.status_label = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.status_label.grid(row=0, column=6, padx=10)
        
        # Simulation toggle button
        self.simulate_btn = ttk.Button(conn_frame, text="Simulate Input: OFF", command=self.toggle_simulation)
        self.simulate_btn.grid(row=0, column=7, padx=5)
        
        # Pin display frame
        pin_frame = ttk.LabelFrame(self.root, text="Pin Status", padding=10)
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
        
        # Statistics frame
        stats_frame = ttk.LabelFrame(self.root, text="Pump Statistics", padding=10)
        stats_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        headers = ["Pump", "Triggers", "Total Units", "Desired µL", "Delivered µL", "Total µL"]
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
            desired_entry.bind('<FocusIn>', lambda e: e.widget.select_range(0, tk.END))  # Select all on focus
            
            delivered_label = ttk.Label(stats_frame, textvariable=self.pump_stats[pump_num]["delivered_unit_size"])
            delivered_label.grid(row=i, column=4, padx=5, pady=2)
            
            total_label = ttk.Label(stats_frame, textvariable=self.pump_stats[pump_num]["total_delivered"])
            total_label.grid(row=i, column=5, padx=5, pady=2)
            
            self.stats_labels[pump_num] = {
                "triggers": triggers_label,
                "units": units_label
            }
        
        # Position frame
        position_frame = ttk.LabelFrame(self.root, text="Plunger Positions", padding=10)
        position_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        self.position_labels = {}
        self.position_bars = {}
        
        for i, pump_num in enumerate([1, 2, 3]):
            pump_color = {1: "blue", 2: "green", 3: "purple"}[pump_num]
            
            ttk.Label(position_frame, text=f"Pump {pump_num}:", foreground=pump_color, font=("Arial", 10, "bold")).grid(row=i, column=0, sticky=tk.W, padx=5, pady=5)
            
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
        
        ttk.Button(button_frame, text="Reset Stats", command=self.reset_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Test Direction Pin", command=self.test_direction_pin).pack(side=tk.LEFT, padx=5)

        # Activity log
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=100, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags for colors
        self.log_text.tag_config("trigger", foreground="blue")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("system", foreground="green")
        self.log_text.tag_config("position", foreground="purple")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(5, weight=1)
        

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)
    
    def toggle_connection(self):
        if self.serial_connection and self.serial_connection.is_open:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        port = self.port_combo.get()
        baud = int(self.baud_combo.get())
        
        try:
            self.serial_connection = serial.Serial(port, baud, timeout=1)
            self.connection_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.status_label.config(text="Connected", foreground="green")
            self.connect_btn.config(text="Disconnect")
            self.log_message(f"Connected to {port} at {baud} baud", "system")

            # Wait for Arduino to finish initialization
            time.sleep(2)  # Increased from 0.5 to 2 seconds
            # sync current desired sizes with Arduino
            time.sleep(0.5)  # Give Arduino time to initialize
            # Sync current desired sizes with Arduino
            for pump_num in [1, 2, 3]:
                desired = float(self.pump_stats[pump_num]["desired_unit_size"].get())
                command = f"!SetUnitSize {pump_num} {desired}\r\n"
                self.serial_connection.write(command.encode())
                self.serial_connection.flush()
                time.sleep(0.2)  # Increased delay
                self.log_message(f"Pump {pump_num}: Synced unit size to {desired:.3f} µL", "system")
            
            self.stop_reading = False
            self.reading_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.reading_thread.start()
            
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def read_serial(self):
        """Read serial data from Arduino in separate thread"""
        buffer = b""
        
        while not self.stop_reading and self.serial_connection and self.serial_connection.is_open:
            try:
                if self.serial_connection.in_waiting > 0:
                    raw_data = self.serial_connection.read(self.serial_connection.in_waiting)
                    buffer += raw_data
                    
                    while b'\n' in buffer:
                        line_bytes, buffer = buffer.split(b'\n', 1)
                        
                        # Be more careful with decoding - only decode valid ASCII/UTF-8
                        try:
                            line = line_bytes.decode('utf-8').strip()
                        except UnicodeDecodeError:
                            # Skip corrupted lines
                            continue
                        
                        if line:
                            try:
                                json_data = json.loads(line)
                                # Process trigger immediately on serial thread
                                if json_data.get("type") == "trigger":
                                    self.handle_json_message(json_data)
                                else:
                                    self.root.after(0, self.handle_json_message, json_data)
                            except json.JSONDecodeError:
                                if len(line) == 7 and all(c in '01' for c in line):
                                    self.root.after(0, self.decode_pins, line)
                else:
                    time.sleep(0.01)
                    
            except Exception as e:
                self.root.after(0, self.log_message, f"Serial read error: {e}", "error")
                time.sleep(0.1)

    def handle_json_message(self, json_data):
        """Process JSON messages from Arduino"""
        msg_type = json_data.get("type", "unknown")
        
        if msg_type == "trigger":
            pump = json_data.get("pump", "?")
            magnitude = json_data.get("magnitude", "?")
            volume = json_data.get("volume", "?")
            binary = json_data.get("binary", "")
            self.log_message(f"Trigger: Pump {pump}, Magnitude {magnitude}, Volume {volume} µL", "trigger")
            if isinstance(pump, int) and isinstance(magnitude, int):
                self.root.after(0, self.update_statistics, pump, magnitude)
            
        elif msg_type == "complete":
            pump = json_data.get("pump", "?")
            volume = json_data.get("volume", "?")
            position = json_data.get("position", "?")
            direction = json_data.get("direction", "?")
            self.log_message(f"Complete: Pump {pump} delivered {volume} µL at {position} mm ({direction})", "system")
            
            # Sync position and direction directly from Arduino
            if isinstance(pump, int) and isinstance(position, (int, float)):
                stats = self.pump_stats[pump]
                stats["position_mm"] = float(position)
                stats["direction"] = 1 if direction == "F" else -1
                
                if isinstance(volume, (int, float)):
                    total = float(stats["total_delivered"].get()) + volume
                    stats["total_delivered"].set(f"{total:.3f}")
                
                self.root.after(0, self.update_position_displays)
                self.save_state()
                
        elif msg_type == "error":
            message = json_data.get("message", "Unknown error")
            self.log_message(f"Arduino Error: {message}", "error")
            
        elif msg_type == "status":
            message = json_data.get("message", "")
            pump = json_data.get("pump", None)
            if pump:
                self.log_message(f"Pump {pump}: {message}", "system")
            else:
                self.log_message(f"Arduino: {message}", "system")

        elif msg_type == "warning":
            message = json_data.get("message", "Unknown warning")
            self.log_message(f"Arduino Warning: {message}", "error")
    
    def disconnect(self):
        self.stop_reading = True
        if self.reading_thread:
            self.reading_thread.join(timeout=2)
        
        if self.serial_connection:
            self.serial_connection.close()
        
        self.status_label.config(text="Disconnected", foreground="red")
        self.connect_btn.config(text="Connect")
        self.log_message("Disconnected", "system")
    
    def toggle_simulation(self):
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
                self.simulation_timer = None

    def schedule_simulation(self):
        if self.simulation_enabled:
            self.generate_simulated_trigger()
            self.simulation_timer = self.root.after(2000, self.schedule_simulation)

    def send_trigger_to_arduino(self, pump_num, magnitude):
        """Send a manual trigger command to Arduino"""
        if not self.serial_connection or not self.serial_connection.is_open:
            self.log_message("ERROR: Not connected to Arduino", "error")
            return
        
        command = f"!ManualTrigger {pump_num} {magnitude}\r\n"
        
        # Clear any pending data first
        self.serial_connection.reset_input_buffer()
        time.sleep(0.05)
        
        # Send command
        self.serial_connection.write(command.encode())
        self.serial_connection.flush()
        
        # Give Arduino time to process
        time.sleep(0.1)
        
        self.log_message(f"[SIMULATION] Sent trigger to Arduino: Pump {pump_num}, Magnitude {magnitude}", "trigger")

    def generate_simulated_trigger(self):
        import random
        
        pump_num = random.randint(1, 3)
        magnitude = random.randint(1, 16)

        # pump_num = 1
        # magnitude = 1

        pump_encoding = {1: '01', 2: '10', 3: '11'}
        pump_bits = pump_encoding[pump_num]
        
        # Constraint: mag_bits[3] (LSB of magnitude) must equal pump_bits[1]
        # mag_bits[3] = '1' means magnitude value (after -1) is odd → original magnitude is EVEN
        # mag_bits[3] = '0' means magnitude value (after -1) is even → original magnitude is ODD
        #
        # Pump 1 = '01' → pump_bits[1] = '1' → need mag_bits[3] = '1' → magnitude must be EVEN
        # Pump 2 = '10' → pump_bits[1] = '0' → need mag_bits[3] = '0' → magnitude must be ODD
        # Pump 3 = '11' → pump_bits[1] = '1' → need mag_bits[3] = '1' → magnitude must be EVEN
        
        # Adjust magnitude to satisfy constraint
        if pump_bits[1] == '1':  # Need mag_bits[3] = '1' → magnitude must be EVEN
            if magnitude % 2 == 1:  # Currently odd, make even
                magnitude = magnitude + 1 if magnitude < 16 else magnitude - 1
        else:  # pump_bits[1] == '0', need mag_bits[3] = '0' → magnitude must be ODD
            if magnitude % 2 == 0:  # Currently even, make odd
                magnitude = magnitude + 1 if magnitude < 16 else magnitude - 1
        
        mag_value = magnitude - 1
        mag_bits = format(mag_value, '04b')
        
        # Build bit string
        bit_string_list = ['0'] * 7
        bit_string_list[0] = '0'  # Pin 8
        bit_string_list[1] = '0'  # Unused
        bit_string_list[2] = pump_bits[0]
        bit_string_list[3] = pump_bits[1]  # This equals mag_bits[3] by design
        bit_string_list[4] = mag_bits[2]
        bit_string_list[5] = mag_bits[1]
        bit_string_list[6] = mag_bits[0]
        
        bit_string = ''.join(bit_string_list)
        
        # simulate Arduino JSON output
        simulated_json = {
            "type": "trigger",
            "pump": pump_num,
            "magnitude": magnitude,
            "volume": magnitude * 55.0,  # Use default 55µL from Arduino
            "position": 0.0,  # Placeholder
            "direction": "F",
            "binary": bit_string
        }
        
        self.log_message(f"[SIMULATED] Pump {pump_num}, Magnitude {magnitude}", "trigger")
    
        self.decode_pins(bit_string)
        # Also send to Arduino if connected
        self.send_trigger_to_arduino(pump_num, magnitude)

    def process_data(self, data):
        if len(data) == 7 and all(c in '01' for c in data):
            self.decode_pins(data)
    
    def decode_pins(self, bit_string):
        self.binary_label.config(text=bit_string)
        
        # Decode magnitude from pins 2-5 (indices 6,5,4,3)
        mag_bits = bit_string[6] + bit_string[5] + bit_string[4] + bit_string[3]
        magnitude = int(mag_bits, 2) + 1
        self.magnitude_label.config(text=str(magnitude))
        
        # Decode pump from pins 6-7 (indices 2,1)
        pump_bits = bit_string[2:4]
        pump_map = {'01': 1, '10': 2, '11': 3}
               
        if pump_bits in pump_map:
            pump_num = pump_map[pump_bits]
            pump_color = {1: "blue", 2: "green", 3: "purple"}[pump_num]
            self.pump_label.config(text=f"Pump {pump_num}", foreground=pump_color)
            
            self.trigger_led()
            self.update_statistics(pump_num, magnitude)
            self.log_message(f"Trigger: Pump {pump_num}, Magnitude {magnitude}", "trigger")
        else:
            self.pump_label.config(text="Invalid", foreground="red")
            self.log_message(f"Invalid pump encoding: {pump_bits}", "error")
    
    def trigger_led(self):
        self.total_triggers += 1
        self.trigger_count_label.config(text=str(self.total_triggers))
        
        self.led_canvas.itemconfig(self.led_indicator, fill="green", outline="darkgreen")
        self.led_active = True
        self.root.after(200, self.reset_led)
    
    def reset_led(self):
        self.led_canvas.itemconfig(self.led_indicator, fill="red", outline="darkred")
        self.led_active = False
    
    def update_statistics(self, pump_num, magnitude):
        stats = self.pump_stats[pump_num]
        
        stats["triggers"] += 1
        stats["total_units"] += magnitude
        
        self.stats_labels[pump_num]["triggers"].config(text=str(stats["triggers"]))
        self.stats_labels[pump_num]["units"].config(text=str(stats["total_units"]))
        
        desired_ul = float(stats["desired_unit_size"].get())
        delivered_ul = self.calculate_discrete_volume(desired_ul)
        
        stats["delivered_unit_size"].set(f"{delivered_ul:.3f}")
        
        total_delivered = stats["triggers"] * delivered_ul
        stats["total_delivered"].set(f"{total_delivered:.3f}")
    
    def calculate_discrete_volume(self, desired_ul):
        steps_needed = desired_ul / self.UL_PER_STEP
        steps_actual = int(steps_needed) if steps_needed == int(steps_needed) else int(steps_needed) + 1
        return round(steps_actual * self.UL_PER_STEP, 3)
    
    def update_plunger_position(self, pump_num, delivered_ul):
        stats = self.pump_stats[pump_num]
        position_mm = stats["position_mm"]
        direction = stats["direction"]
        
        distance_mm = (delivered_ul / 1000) / self.ML_PER_MM
        new_position = position_mm + (distance_mm * direction)
        
        if new_position >= self.MAX_TRAVEL_MM:
            stats["direction"] = -1
            stats["position_mm"] = self.MAX_TRAVEL_MM
            self.log_message(f"Pump {pump_num}: Reached max travel, reversing direction", "position")
        elif new_position <= 0:
            stats["direction"] = 1
            stats["position_mm"] = 0.0
            self.log_message(f"Pump {pump_num}: Reached min position, reversing direction", "position")
        else:
            stats["position_mm"] = new_position
        
        self.update_position_displays()
        self.save_state()
    
    def update_position_displays(self):
        for pump_num in [1, 2, 3]:
            stats = self.pump_stats[pump_num]
            position = stats["position_mm"]
            direction_text = "Forward" if stats["direction"] == 1 else "Reverse"
            
            self.position_labels[pump_num].config(text=f"{position:.2f} mm ({direction_text})")
            self.position_bars[pump_num]['value'] = position
    
    def update_desired_size(self, pump_num):
        try:
            desired = float(self.pump_stats[pump_num]["desired_unit_size"].get())
            if desired <= 0:
                raise ValueError("Must be positive")

            # Log the change with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.desired_ul_history[pump_num].append((timestamp, desired))

            # SEND COMMAND TO ARDUINO
            if self.serial_connection and self.serial_connection.is_open:
                command = f"!SetUnitSize {pump_num} {desired}\r\n"
                print(f"DEBUG: Sending: {repr(command)}")  # ADD THIS
                self.serial_connection.write(command.encode())
                self.serial_connection.flush()  # ADD THIS - force send
                self.log_message(f"Pump {pump_num}: Sent unit size update to Arduino: {desired:.3f} µL", "system")
                
            self.save_state()
            self.log_message(f"Pump {pump_num}: Desired unit size updated to {desired:.3f} µL", "system")
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter a valid positive number")
            self.pump_stats[pump_num]["desired_unit_size"].set("10.0")
    
    def set_position_dialog(self, pump_num):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Set Pump {pump_num} Position")
        dialog.geometry("300x150")
        dialog.transient(self.root)  # Keep dialog on top of main window
        dialog.grab_set()  # Make dialog modal
        
        ttk.Label(dialog, text="Position (0-40 mm):").grid(row=0, column=0, padx=10, pady=10, sticky=tk.W)
        pos_entry = ttk.Entry(dialog)
        pos_entry.insert(0, f"{self.pump_stats[pump_num]['position_mm']:.2f}")
        pos_entry.grid(row=0, column=1, padx=10, pady=10)
        pos_entry.select_range(0, tk.END)  # Select all text
        pos_entry.focus_set()  # Set focus to entry
        
        ttk.Label(dialog, text="Direction:").grid(row=1, column=0, padx=10, pady=10, sticky=tk.W)
        dir_var = tk.StringVar(value="Forward" if self.pump_stats[pump_num]['direction'] == 1 else "Reverse")
        dir_combo = ttk.Combobox(dialog, textvariable=dir_var, values=["Forward", "Reverse"], state='readonly')
        dir_combo.grid(row=1, column=1, padx=10, pady=10)
        
        def apply():
            try:
                new_pos = float(pos_entry.get())
                if not (0 <= new_pos <= self.MAX_TRAVEL_MM):
                    raise ValueError("Position out of range")
                
                new_dir = 1 if dir_var.get() == "Forward" else -1
                dir_str = "F" if dir_var.get() == "Forward" else "R"
                
                self.pump_stats[pump_num]['position_mm'] = new_pos
                self.pump_stats[pump_num]['direction'] = new_dir
                
                # Sync to Arduino
                if self.serial_connection and self.serial_connection.is_open:
                    self.serial_connection.write(f"!SetCurrentPosition {pump_num} {new_pos}\r\n".encode())
                    self.serial_connection.flush()
                    time.sleep(0.1)
                    self.serial_connection.write(f"!SetDirection {pump_num} {dir_str}\r\n".encode())
                    self.serial_connection.flush()
                
                self.update_position_displays()
                self.save_state()
                self.log_message(f"Pump {pump_num}: Position set to {new_pos:.2f} mm ({dir_var.get()})", "position")
                dialog.destroy()
                
            except ValueError as e:
                messagebox.showerror("Invalid Input", f"Please enter a valid position (0-40): {e}")
        
        def on_enter(event):
            apply()
        
        pos_entry.bind('<Return>', on_enter)
        dir_combo.bind('<Return>', on_enter)
        
        apply_btn = ttk.Button(dialog, text="Apply", command=apply)
        apply_btn.grid(row=2, column=0, columnspan=2, pady=10)
        
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

    def reset_stats(self):
        if messagebox.askyesno("Reset Statistics", "Reset all pump statistics (positions will be preserved)?"):
            for pump_num in [1, 2, 3]:
                self.pump_stats[pump_num]["triggers"] = 0
                self.pump_stats[pump_num]["total_units"] = 0
                self.pump_stats[pump_num]["delivered_unit_size"].set("0.0")
                self.pump_stats[pump_num]["total_delivered"].set("0.0")
                
                self.stats_labels[pump_num]["triggers"].config(text="0")
                self.stats_labels[pump_num]["units"].config(text="0")
            
            self.total_triggers = 0
            self.trigger_count_label.config(text="0")
            
            self.save_state()  # ADD THIS to persist the reset
    
    def export_csv(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=self.script_dir,
            initialfile=f"pump_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
        
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(["Timestamp", "Pump", "Triggers", "Total Units", "Desired uL", "Delivered uL", "Total uL", "Position mm", "Direction"])
                    
                    # Get all unique timestamps from history
                    all_timestamps = set()
                    for pump_num in [1, 2, 3]:
                        for timestamp, _ in self.desired_ul_history[pump_num]:
                            all_timestamps.add(timestamp)
                    
                    # Sort timestamps
                    sorted_timestamps = sorted(all_timestamps)
                    
                    # Write rows for each timestamp
                    for timestamp in sorted_timestamps:
                        for pump_num in [1, 2, 3]:
                            stats = self.pump_stats[pump_num]
                            direction_text = "Forward" if stats["direction"] == 1 else "Reverse"
                            
                            # Find desired µL at this timestamp
                            desired_ul = stats["desired_unit_size"].get()
                            for ts, value in reversed(self.desired_ul_history[pump_num]):
                                if ts <= timestamp:
                                    desired_ul = value
                                    break
                            
                            writer.writerow([
                                timestamp,
                                pump_num,
                                stats["triggers"],
                                stats["total_units"],
                                f"{desired_ul:.3f}",
                                stats["delivered_unit_size"].get(),
                                stats["total_delivered"].get(),
                                f"{stats['position_mm']:.2f}",
                                direction_text
                            ])
                    
                    self.log_message(f"Statistics exported to {filename}", "system")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))
    
    def clear_log(self):
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

    def test_direction_pin(self):
        """Test direction pin toggle"""
        if not self.serial_connection or not self.serial_connection.is_open:
            messagebox.showerror("Error", "Not connected to Arduino")
            return
        
        command = b"!TestDirection 1\r\n"
        self.serial_connection.write(command)
        self.log_message("Sent TestDirection command to Pump 1", "system")
    
    def log_message(self, message, tag=""):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, log_entry, tag)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
    
    def save_state(self):
        state = {
            "pumps": {},
            "desired_ul_history": {}
        }
        
        for pump_num in [1, 2, 3]:
            stats = self.pump_stats[pump_num]
            state["pumps"][pump_num] = {
                "position_mm": stats["position_mm"],
                "direction": stats["direction"],
                "desired_unit_size": stats["desired_unit_size"].get()
            }
            # Convert tuples to lists for JSON serialization
            state["desired_ul_history"][pump_num] = [
                list(entry) for entry in self.desired_ul_history[pump_num]
            ]
        
        state_file = os.path.join(self.script_dir, "pump_state.json")
        try:
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.log_message(f"Error saving state: {e}", "error")

    def load_state(self):
        state_file = os.path.join(self.script_dir, "pump_state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                for pump_num_str, pump_data in state.get("pumps", {}).items():
                    pump_num = int(pump_num_str)
                    if pump_num in self.pump_stats:
                        self.pump_stats[pump_num]["position_mm"] = pump_data.get("position_mm", 0.0)
                        self.pump_stats[pump_num]["direction"] = pump_data.get("direction", 1)
                        self.pump_stats[pump_num]["desired_unit_size"].set(pump_data.get("desired_unit_size", "10.0"))
                
                # Load history and convert lists back to tuples
                for pump_num_str, history in state.get("desired_ul_history", {}).items():
                    pump_num = int(pump_num_str)
                    if pump_num in self.desired_ul_history:
                        self.desired_ul_history[pump_num] = [
                            tuple(entry) for entry in history
                        ]
                
                # Ensure all pumps have initialized history (in case state file is old)
                for pump_num in [1, 2, 3]:
                    if pump_num not in self.desired_ul_history or not self.desired_ul_history[pump_num]:
                        # Initialize with current desired size
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        desired = float(self.pump_stats[pump_num]["desired_unit_size"].get())
                        self.desired_ul_history[pump_num] = [(timestamp, desired)]
                
            except Exception as e:
                print(f"Error loading state: {e}")
    
    def save_log_to_file(self):
        if not self.connection_timestamp:
            return
        
        log_dir = os.path.join(self.script_dir, "PumpMonitorLogs")
        os.makedirs(log_dir, exist_ok=True)
        
        filename = os.path.join(log_dir, f"pump_log_{self.connection_timestamp}.txt")
        
        try:
            log_content = self.log_text.get(1.0, tk.END)
            # Convert µL to uL for file compatibility
            log_content = log_content.replace('µL', 'uL')
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(log_content)
            
            print(f"Log saved to {filename}")
        except Exception as e:
            print(f"Error saving log: {e}")
    
    def on_closing(self):
        # Stop simulation if running
        if self.simulation_enabled:
            self.simulation_enabled = False
            if self.simulation_timer:
                self.root.after_cancel(self.simulation_timer)
        
        # Disconnect if connected
        if self.serial_connection and self.serial_connection.is_open:
            self.disconnect()
        
        # Save state
        self.save_state()
        
        # Save log
        self.save_log_to_file()
        
        self.root.destroy()
        
    def fix_initial_focus(self):
        """Ensure window gets proper focus on launch across platforms"""
        self.root.update_idletasks()
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        
        # Platform-specific handling
        import platform
        system = platform.system()
        
        if system == 'Darwin':  # macOS
            try:
                import subprocess
                subprocess.run(['osascript', '-e', 
                              'tell application "System Events" to set frontmost of process "Python" to true'],
                              check=False, capture_output=True)
            except:
                pass
        elif system == 'Windows':
            try:
                self.root.attributes('-topmost', True)
                self.root.after(100, lambda: self.root.attributes('-topmost', False))
            except:
                pass
        
        # Give focus to the port combobox
        self.root.after(150, lambda: self.port_combo.focus_set())

if __name__ == "__main__":
    root = tk.Tk()
    app = PumpMonitorGUI(root)
    root.mainloop()
