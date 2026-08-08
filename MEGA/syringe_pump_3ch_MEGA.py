# syringe_pump_3ch_MEGA.py


#!/usr/bin/env python3
"""
Raspberry Pi Syringe Pump Monitor - Arduino Mega Version
Receives position/volume updates via USB serial and logs data
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import json
import threading
import time
from datetime import datetime
from pathlib import Path

class PumpMonitorMega:
    def __init__(self, root):
        self.root = root
        self.root.title("Pump Monitor - Arduino Mega")
        self.root.geometry("1100x900")
        
        # Pump mechanics
        self.MM_PER_STEP = 0.004  # 0.8mm pitch / 200 steps
        self.ML_PER_MM = 0.20
        self.UL_PER_STEP = self.MM_PER_STEP * self.ML_PER_MM * 1000  # 0.8 µL/step
        self.MAX_TRAVEL_MM = 40.0
        
        # Serial connection
        self.serial_port = None
        self.connected = False
        self.read_thread = None
        self.running = False
        
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
                "last_magnitude": 0,
                "last_volume": 0.0
            }
            self.pump_positions[pump_num] = 0.0
            self.pump_directions[pump_num] = "Forward"
        
        # State file
        self.state_file = Path(__file__).parent / "pump_state_mega.json"
        
        # Log directory
        self.log_dir = Path(__file__).parent / "PumpMonitorLogs"
        self.log_dir.mkdir(exist_ok=True)
        
        # Activity log storage
        self.activity_log = []
        
        # Connection status
        self.last_update_time = time.time()
        self.connection_timeout = 5.0  # seconds
        
        self.create_widgets()
        self.load_state()
        
        # Fix initial focus
        self.root.after(100, self.fix_initial_focus)
        
        # Start connection watchdog
        self.check_connection_status()
        
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
        conn_frame = ttk.LabelFrame(self.root, text="Arduino Mega Connection", padding=10)
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
        
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5)
        
        self.status_label = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.status_label.grid(row=0, column=6, padx=10)
        
        # Last update indicator
        ttk.Label(conn_frame, text="Last Update:").grid(row=0, column=7, sticky=tk.W, padx=(20,0))
        self.last_update_label = ttk.Label(conn_frame, text="Never", font=("Arial", 9))
        self.last_update_label.grid(row=0, column=8, padx=5)
        
        # Pin display frame
        pin_frame = ttk.LabelFrame(self.root, text="Current Trigger", padding=10)
        pin_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=10, pady=5)
        
        ttk.Label(pin_frame, text="Binary Code:").grid(row=0, column=0, sticky=tk.W)
        self.binary_label = ttk.Label(pin_frame, text="00000000", font=("Courier", 12, "bold"))
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
            desired_entry.bind('<FocusIn>', lambda e: e.widget.select_range(0, tk.END))
            
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
            
            pos_label = ttk.Label(position_frame, text="0.000 mm (Forward)", font=("Arial", 9))
            pos_label.grid(row=i, column=1, sticky=tk.W, padx=10)
            self.position_labels[pump_num] = pos_label
            
            progress = ttk.Progressbar(position_frame, length=300, mode='determinate', maximum=self.MAX_TRAVEL_MM)
            progress.grid(row=i, column=2, padx=10)
            self.position_bars[pump_num] = progress
            
            ttk.Button(position_frame, text="Request Position", command=lambda p=pump_num: self.request_position(p)).grid(row=i, column=3, padx=5)
        
        self.update_position_displays()
        
        # Control buttons frame
        button_frame = ttk.Frame(self.root)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, text="Request Status", command=self.request_status).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Home All Pumps", command=self.home_all_pumps).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Reset Stats", command=self.reset_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT, padx=5)
        
        # Activity log
        log_frame = ttk.LabelFrame(self.root, text="Activity Log", padding=10)
        log_frame.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=110, state='disabled')
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # Configure text tags
        self.log_text.tag_config("trigger", foreground="blue")
        self.log_text.tag_config("complete", foreground="green")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("system", foreground="orange")
        self.log_text.tag_config("position", foreground="purple")
        self.log_text.tag_config("status", foreground="gray")
        
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
    
    def toggle_connection(self):
        """Connect/disconnect to Arduino Mega"""
        if not self.connected:
            try:
                port = self.port_combo.get()
                baud = int(self.baud_combo.get())
                
                self.serial_port = serial.Serial(port, baud, timeout=0.1)
                time.sleep(2)  # Wait for Arduino reset
                
                self.connected = True
                self.running = True
                self.connect_btn.config(text="Disconnect")
                self.status_label.config(text="Connected", foreground="green")
                
                # Start read thread
                self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
                self.read_thread.start()
                
                self.log_message("Arduino Mega connected", "system")
                
                # Request initial status
                self.root.after(1000, self.request_status)
                
            except Exception as e:
                messagebox.showerror("Connection Error", f"Failed to connect:\n{e}")
        else:
            self.disconnect()
    
    def disconnect(self):
        """Disconnect from Arduino"""
        self.running = False
        
        if self.read_thread:
            self.read_thread.join(timeout=1.0)
        
        if self.serial_port:
            self.serial_port.close()
            self.serial_port = None
        
        self.connected = False
        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Disconnected", foreground="red")
        self.log_message("Arduino Mega disconnected", "system")
    
    def read_serial(self):
        """Read and parse JSON messages from Arduino"""
        while self.running:
            try:
                if self.serial_port and self.serial_port.in_waiting:
                    line = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                    
                    if line:
                        self.parse_message(line)
                        self.last_update_time = time.time()
                        self.root.after(0, self.update_last_update_label)
                
                time.sleep(0.01)  # Small delay to prevent CPU spinning
                
            except Exception as e:
                self.root.after(0, lambda: self.log_message(f"Serial read error: {e}", "error"))
                time.sleep(0.1)
    
    def parse_message(self, message):
        """Parse JSON message from Arduino"""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")
            
            if msg_type == "trigger":
                self.handle_trigger(data)
            elif msg_type == "complete":
                self.handle_complete(data)
            elif msg_type == "status":
                self.handle_status(data)
            elif msg_type == "error":
                self.handle_error(data)
            else:
                self.root.after(0, lambda: self.log_message(f"Unknown message: {message}", "error"))
                
        except json.JSONDecodeError:
            self.root.after(0, lambda: self.log_message(f"Invalid JSON: {message}", "error"))
        except Exception as e:
            self.root.after(0, lambda: self.log_message(f"Parse error: {e}", "error"))
    
    def handle_trigger(self, data):
        """Handle trigger event from Arduino"""
        # Expected: {"type":"trigger","pump":1,"magnitude":8,"volume":1024.0,"position":15.234,"direction":"F","binary":"01011000"}
        
        pump_num = data.get("pump", 0)
        magnitude = data.get("magnitude", 0)
        volume = data.get("volume", 0.0)
        position = data.get("position", 0.0)
        direction = data.get("direction", "F")
        binary = data.get("binary", "00000000")
        
        if pump_num not in [1, 2, 3]:
            self.root.after(0, lambda: self.log_message(f"Invalid pump number: {pump_num}", "error"))
            return
        
        # Update GUI in main thread
        self.root.after(0, lambda: self._update_trigger_display(pump_num, magnitude, volume, position, direction, binary))
    
    def _update_trigger_display(self, pump_num, magnitude, volume, position, direction, binary):
        """Update GUI for trigger event (runs in main thread)"""
        # Flash LED
        self.flash_trigger_led()
        
        # Update trigger count
        self.trigger_count += 1
        self.trigger_count_label.config(text=str(self.trigger_count))
        
        # Update binary display
        self.binary_label.config(text=binary)
        self.magnitude_label.config(text=str(magnitude))
        
        # Update pump label
        pump_color = {1: "blue", 2: "green", 3: "purple"}[pump_num]
        self.pump_label.config(text=f"Pump {pump_num}", foreground=pump_color)
        
        # Update statistics
        self.pump_stats[pump_num]["triggers"] += 1
        self.pump_stats[pump_num]["total_units"] += magnitude
        self.pump_stats[pump_num]["last_magnitude"] = magnitude
        self.pump_stats[pump_num]["last_volume"] = volume
        
        self.stats_labels[pump_num]["triggers"].config(text=str(self.pump_stats[pump_num]["triggers"]))
        self.stats_labels[pump_num]["units"].config(text=str(self.pump_stats[pump_num]["total_units"]))
        
        # Update total delivered
        current_total = float(self.pump_stats[pump_num]["total_delivered"].get())
        new_total = current_total + volume
        self.pump_stats[pump_num]["total_delivered"].set(f"{new_total:.1f}")
        
        # Update position
        self.pump_positions[pump_num] = position
        self.pump_directions[pump_num] = "Forward" if direction == "F" else "Reverse"
        self.update_position_displays()
        
        # Log activity
        self.log_message(f"Trigger: Pump {pump_num}, Magnitude {magnitude}, Volume {volume:.1f} uL, Position {position:.3f} mm", "trigger")
        
        self.save_state()
    
    def handle_complete(self, data):
        """Handle movement complete event from Arduino"""
        # Expected: {"type":"complete","pump":1,"volume":1024.0,"position":15.234}
        
        pump_num = data.get("pump", 0)
        volume = data.get("volume", 0.0)
        position = data.get("position", 0.0)
        
        if pump_num not in [1, 2, 3]:
            return
        
        self.root.after(0, lambda: self._update_complete_display(pump_num, volume, position))
    
    def _update_complete_display(self, pump_num, volume, position):
        """Update GUI for movement complete (runs in main thread)"""
        self.pump_positions[pump_num] = position
        self.update_position_displays()
        
        self.log_message(f"Complete: Pump {pump_num}, Volume {volume:.1f} uL, Final Position {position:.3f} mm", "complete")
        
        self.save_state()
    
    def handle_status(self, data):
        """Handle status update from Arduino"""
        # Expected: {"type":"status","pumps":[{"pump":1,"position":15.234,"direction":"F"},{"pump":2,"position":23.456,"direction":"R"},{"pump":3,"position":8.123,"direction":"F"}]}
        
        pumps_data = data.get("pumps", [])
        
        for pump_data in pumps_data:
            pump_num = pump_data.get("pump", 0)
            if pump_num in [1, 2, 3]:
                position = pump_data.get("position", 0.0)
                direction = pump_data.get("direction", "F")
                
                self.pump_positions[pump_num] = position
                self.pump_directions[pump_num] = "Forward" if direction == "F" else "Reverse"
        
        self.root.after(0, lambda: self.update_position_displays())
        self.root.after(0, lambda: self.log_message("Status update received", "status"))
    
    def handle_error(self, data):
        """Handle error message from Arduino"""
        # Expected: {"type":"error","pump":1,"message":"Limit reached"}
        
        pump_num = data.get("pump", 0)
        message = data.get("message", "Unknown error")
        
        self.root.after(0, lambda: self.log_message(f"Arduino Error - Pump {pump_num}: {message}", "error"))
    
    def send_command(self, command):
        """Send command to Arduino"""
        if self.connected and self.serial_port:
            try:
                self.serial_port.write(f"{command}\n".encode())
                self.log_message(f"Command sent: {command}", "system")
            except Exception as e:
                self.log_message(f"Failed to send command: {e}", "error")
        else:
            messagebox.showwarning("Not Connected", "Arduino not connected")
    
    def request_status(self):
        """Request status from Arduino"""
        self.send_command("?")
    
    def request_position(self, pump_num):
        """Request position for specific pump"""
        self.send_command(f"P,{pump_num}")
    
    def home_all_pumps(self):
        """Send home all pumps command"""
        result = messagebox.askyesno("Home All Pumps", 
                                      "This will home all pumps to their zero position.\n\n"
                                      "Ensure pumps are ready to move.\n\n"
                                      "Continue?")
        if result:
            self.send_command("H")
            self.log_message("Homing all pumps...", "system")
    
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
    
    def calculate_discrete_volume(self, desired_ul):
        """Calculate actual deliverable volume in discrete steps"""
        steps_needed = desired_ul / self.UL_PER_STEP
        steps_actual = int(steps_needed) if steps_needed == int(steps_needed) else int(steps_needed) + 1
        return round(steps_actual * self.UL_PER_STEP, 1)
    
    def update_position_displays(self):
        """Update position labels and progress bars"""
        for pump_num in [1, 2, 3]:
            position = self.pump_positions[pump_num]
            direction = self.pump_directions[pump_num]
            
            self.position_labels[pump_num].config(text=f"{position:.3f} mm ({direction})")
            self.position_bars[pump_num]['value'] = position
    
    def update_last_update_label(self):
        """Update last update timestamp"""
        elapsed = time.time() - self.last_update_time
        if elapsed < 1:
            self.last_update_label.config(text="Just now", foreground="green")
        elif elapsed < 60:
            self.last_update_label.config(text=f"{int(elapsed)}s ago", foreground="green")
        else:
            self.last_update_label.config(text=f"{int(elapsed/60)}m ago", foreground="orange")
    
    def check_connection_status(self):
        """Check if connection is still alive"""
        if self.connected:
            elapsed = time.time() - self.last_update_time
            
            if elapsed > self.connection_timeout:
                self.status_label.config(text="Connected (No Data)", foreground="orange")
            else:
                self.status_label.config(text="Connected", foreground="green")
        
        # Update last update label
        self.update_last_update_label()
        
        # Schedule next check
        self.root.after(1000, self.check_connection_status)
    
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
                
                self.stats_labels[pump_num]["triggers"].config(text="0")
                self.stats_labels[pump_num]["units"].config(text="0")
            
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
                f.write("Pump,Triggers,Total Units,Desired uL,Delivered uL,Total uL,Current Position mm,Direction\n")
                
                for pump_num in [1, 2, 3]:
                    triggers = self.pump_stats[pump_num]["triggers"]
                    units = self.pump_stats[pump_num]["total_units"]
                    desired = self.pump_stats[pump_num]["desired_unit_size"].get()
                    delivered = self.pump_stats[pump_num]["delivered_unit_size"].get()
                    total = self.pump_stats[pump_num]["total_delivered"].get()
                    position = self.pump_positions[pump_num]
                    direction = self.pump_directions[pump_num]
                    
                    f.write(f"{pump_num},{triggers},{units},{desired},{delivered},{total},{position:.3f},{direction}\n")
            
            self.log_message(f"Statistics exported to {filename.name}", "system")
            messagebox.showinfo("Export Complete", f"Statistics saved to:\n{filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export CSV:\n{e}")
    
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
                    f.write(entry.replace('µ', 'u'))
        except:
            pass
        
        # Save state
        self.save_state()
        
        # Disconnect
        if self.connected:
            self.disconnect()
        
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = PumpMonitorMega(root)
    root.mainloop()

