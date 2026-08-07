import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import serial
import serial.tools.list_ports
import threading
import time
from datetime import datetime
import os


class ArduinoSerialGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Arduino Pump Monitor")
        self.root.geometry("1000x850")

        self.serial_port = None
        self.is_connected = False
        self.reading_thread = None

        # Trigger counter
        self.trigger_count = 0
        self.trigger_count_var = tk.StringVar(value="0")

        # Pump statistics and parameters
        self.pump_stats = {
            1: {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),  # ul
                "delivered_unit_size": tk.StringVar(value="0.0"),  # ul (calculated)
                "total_delivered": tk.StringVar(value="0.0")  # ul
            },
            2: {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),
                "delivered_unit_size": tk.StringVar(value="0.0"),
                "total_delivered": tk.StringVar(value="0.0")
            },
            3: {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),
                "delivered_unit_size": tk.StringVar(value="0.0"),
                "total_delivered": tk.StringVar(value="0.0")
            }
        }

        # Current decoded values
        self.current_magnitude = tk.StringVar(value="--")
        self.current_pump = tk.StringVar(value="None")
        self.current_binary = tk.StringVar(value="----")

        # Auto-save directory
        self.log_directory = os.path.join(os.path.expanduser("~"), "PumpMonitorLogs")
        os.makedirs(self.log_directory, exist_ok=True)

        self.create_widgets()
        self.refresh_ports()

    def create_widgets(self):
        # Connection Frame
        conn_frame = ttk.LabelFrame(self.root, text="Connection", padding=10)
        conn_frame.pack(fill="x", padx=10, pady=5)

        # Port selection
        ttk.Label(conn_frame, text="Port:").grid(row=0, column=0, padx=5)
        self.port_combo = ttk.Combobox(conn_frame, width=15, state="readonly")
        self.port_combo.grid(row=0, column=1, padx=5)

        # Baud rate
        ttk.Label(conn_frame, text="Baud Rate:").grid(row=0, column=2, padx=5)
        self.baud_combo = ttk.Combobox(conn_frame, width=10, state="readonly")
        self.baud_combo['values'] = (9600, 19200, 38400, 57600, 115200)
        self.baud_combo.current(0)
        self.baud_combo.grid(row=0, column=3, padx=5)

        # Buttons
        self.refresh_btn = ttk.Button(conn_frame, text="Refresh", command=self.refresh_ports)
        self.refresh_btn.grid(row=0, column=4, padx=5)

        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.grid(row=0, column=5, padx=5)

        # Status label
        self.status_label = ttk.Label(conn_frame, text="Disconnected", foreground="red")
        self.status_label.grid(row=0, column=6, padx=10)

        # Decoded Information Frame
        decoded_frame = ttk.LabelFrame(self.root, text="Current Pump Command", padding=15)
        decoded_frame.pack(fill="x", padx=10, pady=10)

        # Magnitude display
        mag_container = ttk.Frame(decoded_frame)
        mag_container.pack(side="left", padx=30, expand=True)

        ttk.Label(mag_container, text="Magnitude:",
                  font=("Arial", 12, "bold")).pack()
        magnitude_label = tk.Label(mag_container,
                                   textvariable=self.current_magnitude,
                                   font=("Arial", 36, "bold"),
                                   fg="blue",
                                   width=4,
                                   relief="sunken",
                                   borderwidth=3)
        magnitude_label.pack()
        ttk.Label(mag_container, text="units",
                  font=("Arial", 10)).pack()

        # Binary display
        binary_container = ttk.Frame(decoded_frame)
        binary_container.pack(side="left", padx=30, expand=True)

        ttk.Label(binary_container, text="Binary Code:",
                  font=("Arial", 12, "bold")).pack()
        binary_label = tk.Label(binary_container,
                                textvariable=self.current_binary,
                                font=("Courier", 24, "bold"),
                                fg="navy",
                                relief="sunken",
                                borderwidth=3)
        binary_label.pack()
        ttk.Label(binary_container, text="(Pins 2-5)",
                  font=("Arial", 10)).pack()

        # Pump display
        pump_container = ttk.Frame(decoded_frame)
        pump_container.pack(side="left", padx=30, expand=True)

        ttk.Label(pump_container, text="Active Pump:",
                  font=("Arial", 12, "bold")).pack()
        self.pump_label = tk.Label(pump_container,
                                   textvariable=self.current_pump,
                                   font=("Arial", 36, "bold"),
                                   fg="green",
                                   width=8,
                                   relief="sunken",
                                   borderwidth=3)
        self.pump_label.pack()

        # Pump Statistics Frame - EXPANDED
        stats_frame = ttk.LabelFrame(self.root, text="Pump Statistics & Parameters", padding=20)
        stats_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Create statistics display for each pump
        self.pump_stat_labels = {}

        # Header row
        header_frame = ttk.Frame(stats_frame)
        header_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(header_frame, text="", width=20).grid(row=0, column=0)
        ttk.Label(header_frame, text="Pump 1", font=("Arial", 14, "bold"),
                  foreground="blue", width=15).grid(row=0, column=1, padx=10)
        ttk.Label(header_frame, text="Pump 2", font=("Arial", 14, "bold"),
                  foreground="green", width=15).grid(row=0, column=2, padx=10)
        ttk.Label(header_frame, text="Pump 3", font=("Arial", 14, "bold"),
                  foreground="purple", width=15).grid(row=0, column=3, padx=10)

        # Separator
        ttk.Separator(stats_frame, orient='horizontal').pack(fill='x', pady=5)

        # Desired unit size row (EDITABLE)
        desired_frame = ttk.Frame(stats_frame)
        desired_frame.pack(fill="x", pady=5)

        ttk.Label(desired_frame, text="Desired Unit Size (µL):",
                  font=("Arial", 11, "bold"), width=20).grid(row=0, column=0, sticky="w")

        for pump_num in [1, 2, 3]:
            entry_frame = ttk.Frame(desired_frame)
            entry_frame.grid(row=0, column=pump_num, padx=10)

            desired_entry = ttk.Entry(entry_frame,
                                      textvariable=self.pump_stats[pump_num]["desired_unit_size"],
                                      font=("Arial", 12),
                                      width=12,
                                      justify="center")
            desired_entry.pack()

            # Bind to update calculations when changed
            desired_entry.bind('<Return>', lambda e, p=pump_num: self.update_calculations(p))
            desired_entry.bind('<FocusOut>', lambda e, p=pump_num: self.update_calculations(p))

        # Delivered unit size row (CALCULATED)
        delivered_frame = ttk.Frame(stats_frame)
        delivered_frame.pack(fill="x", pady=5)

        ttk.Label(delivered_frame, text="Delivered Unit Size (µL):",
                  font=("Arial", 11, "bold"), width=20).grid(row=0, column=0, sticky="w")

        for pump_num in [1, 2, 3]:
            delivered_label = tk.Label(delivered_frame,
                                       textvariable=self.pump_stats[pump_num]["delivered_unit_size"],
                                       font=("Arial", 12),
                                       fg=self.get_pump_color(pump_num),
                                       width=12,
                                       relief="sunken",
                                       borderwidth=1)
            delivered_label.grid(row=0, column=pump_num, padx=10)

        # Total amount delivered row (CALCULATED)
        total_delivered_frame = ttk.Frame(stats_frame)
        total_delivered_frame.pack(fill="x", pady=5)

        ttk.Label(total_delivered_frame, text="Total Delivered (µL):",
                  font=("Arial", 11, "bold"), width=20).grid(row=0, column=0, sticky="w")

        for pump_num in [1, 2, 3]:
            total_label = tk.Label(total_delivered_frame,
                                   textvariable=self.pump_stats[pump_num]["total_delivered"],
                                   font=("Arial", 12, "bold"),
                                   fg=self.get_pump_color(pump_num),
                                   width=12,
                                   relief="sunken",
                                   borderwidth=2)
            total_label.grid(row=0, column=pump_num, padx=10)

        # Separator
        ttk.Separator(stats_frame, orient='horizontal').pack(fill='x', pady=10)

        # Triggers row
        triggers_frame = ttk.Frame(stats_frame)
        triggers_frame.pack(fill="x", pady=5)

        ttk.Label(triggers_frame, text="Triggers:", font=("Arial", 11, "bold"),
                  width=20).grid(row=0, column=0, sticky="w")

        for pump_num in [1, 2, 3]:
            trigger_label = tk.Label(triggers_frame, text="0",
                                     font=("Arial", 14, "bold"),
                                     fg=self.get_pump_color(pump_num),
                                     width=12,
                                     relief="sunken",
                                     borderwidth=2)
            trigger_label.grid(row=0, column=pump_num, padx=10)

            if pump_num not in self.pump_stat_labels:
                self.pump_stat_labels[pump_num] = {}
            self.pump_stat_labels[pump_num]["triggers"] = trigger_label

        # Total units row
        units_frame = ttk.Frame(stats_frame)
        units_frame.pack(fill="x", pady=5)

        ttk.Label(units_frame, text="Total Units:", font=("Arial", 11, "bold"),
                  width=20).grid(row=0, column=0, sticky="w")

        for pump_num in [1, 2, 3]:
            units_label = tk.Label(units_frame, text="0",
                                   font=("Arial", 14, "bold"),
                                   fg=self.get_pump_color(pump_num),
                                   width=12,
                                   relief="sunken",
                                   borderwidth=2)
            units_label.grid(row=0, column=pump_num, padx=10)
            self.pump_stat_labels[pump_num]["units"] = units_label

        # Average units per trigger row
        avg_frame = ttk.Frame(stats_frame)
        avg_frame.pack(fill="x", pady=5)

        ttk.Label(avg_frame, text="Avg Units/Trigger:", font=("Arial", 11, "bold"),
                  width=20).grid(row=0, column=0, sticky="w")

        for pump_num in [1, 2, 3]:
            avg_label = tk.Label(avg_frame, text="0.0",
                                 font=("Arial", 12),
                                 fg=self.get_pump_color(pump_num),
                                 width=12,
                                 relief="sunken",
                                 borderwidth=1)
            avg_label.grid(row=0, column=pump_num, padx=10)
            self.pump_stat_labels[pump_num]["average"] = avg_label

        # Reset statistics button
        button_frame = ttk.Frame(stats_frame)
        button_frame.pack(pady=15)

        reset_stats_btn = ttk.Button(button_frame, text="Reset All Statistics",
                                     command=self.reset_all_stats)
        reset_stats_btn.pack(side="left", padx=5)

        ttk.Button(button_frame, text="Export Statistics to CSV",
                   command=self.export_stats_csv).pack(side="left", padx=5)

        # Trigger Status and Counter Frame
        trigger_status_frame = ttk.Frame(self.root)
        trigger_status_frame.pack(fill="x", padx=10, pady=5)

        # Trigger LED Indicator Frame (left side)
        trigger_frame = ttk.LabelFrame(trigger_status_frame, text="Trigger Status (Pin 9)", padding=10)
        trigger_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))

        # LED indicator container
        led_container = ttk.Frame(trigger_frame)
        led_container.pack()

        ttk.Label(led_container, text="Trigger LED:",
                  font=("Arial", 10)).pack(side="left", padx=(0, 10))

        # LED indicator (circular canvas)
        self.led_canvas = tk.Canvas(led_container, width=40, height=40,
                                    highlightthickness=0, bg='white')
        self.led_canvas.pack(side="left")

        # Draw LED circle
        self.led_indicator = self.led_canvas.create_oval(5, 5, 35, 35,
                                                         fill="red",
                                                         outline="darkred",
                                                         width=2)

        # Trigger Counter Frame (right side)
        counter_frame = ttk.LabelFrame(trigger_status_frame, text="Total Trigger Counter", padding=10)
        counter_frame.pack(side="right", fill="both", expand=True, padx=(5, 0))

        # Counter display
        counter_display_frame = ttk.Frame(counter_frame)
        counter_display_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(counter_display_frame, text="Total Triggers:",
                  font=("Arial", 10)).pack(side="left", padx=(0, 10))

        counter_label = tk.Label(counter_display_frame,
                                 textvariable=self.trigger_count_var,
                                 font=("Arial", 16, "bold"),
                                 fg="blue",
                                 width=8,
                                 relief="sunken",
                                 borderwidth=2)
        counter_label.pack(side="left")

        # Reset button
        self.reset_btn = ttk.Button(counter_frame, text="Reset Counter",
                                    command=self.reset_counter)
        self.reset_btn.pack()

        # Pump Activity Log Frame
        log_frame = ttk.LabelFrame(self.root, text="Pump Activity Log", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Text area with scrollbar for activity log
        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            width=90,
            height=10,
            font=("Consolas", 9)
        )
        self.log_area.pack(fill="both", expand=True)

        # Log control buttons
        log_control_frame = ttk.Frame(log_frame)
        log_control_frame.pack(fill="x", pady=(5, 0))

        self.clear_log_btn = ttk.Button(log_control_frame, text="Clear Log",
                                        command=self.clear_log)
        self.clear_log_btn.pack(side="left", padx=5)

        self.save_log_btn = ttk.Button(log_control_frame, text="Save Log to File",
                                       command=self.save_log)
        self.save_log_btn.pack(side="left", padx=5)

        # Show log directory
        log_dir_label = ttk.Label(log_control_frame,
                                  text=f"Auto-save location: {self.log_directory}",
                                  font=("Arial", 8),
                                  foreground="gray")
        log_dir_label.pack(side="left", padx=10)

        self.autoscroll_log_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_control_frame, text="Auto-scroll",
                        variable=self.autoscroll_log_var).pack(side="right", padx=5)

    def update_calculations(self, pump_num):
        """Update delivered unit size and total delivered when desired size changes"""
        try:
            desired = float(self.pump_stats[pump_num]["desired_unit_size"].get())

            # For now, delivered = desired (placeholder)
            # In the future, this would be calculated from actual calibration data
            delivered = desired

            triggers = self.pump_stats[pump_num]["triggers"]
            total_units = self.pump_stats[pump_num]["total_units"]

            # Update delivered unit size
            self.pump_stats[pump_num]["delivered_unit_size"].set(f"{delivered:.2f}")

            # Update total delivered (total_units * delivered_unit_size)
            total_delivered = total_units * delivered
            self.pump_stats[pump_num]["total_delivered"].set(f"{total_delivered:.2f}")

        except ValueError:
            # Invalid input, reset to default
            self.pump_stats[pump_num]["desired_unit_size"].set("10.0")
            self.update_calculations(pump_num)

    def get_pump_color(self, pump_num):
        """Return color for pump number"""
        colors = {1: "blue", 2: "green", 3: "purple"}
        return colors.get(pump_num, "black")

    def decode_pump_data(self, pin_data):
        """Decode the 7-bit pin data into magnitude and pump number

        Pin mapping from your table:
        - String format: Pin8 Pin7 Pin6 Pin5 Pin4 Pin3 Pin2
        - Indices:       [0]   [1]   [2]  [3]  [4]  [5]  [6]

        Magnitude: Pins 2-5 (indices 6,5,4,3) - need to reverse for LSB->MSB
        Pump: Pins 6-7 (indices 2,1)
        """
        if len(pin_data) != 7:
            return None, None

        # Pins 2-5 are at indices 6,5,4,3 (rightmost 4 bits)
        # Pin 2 is LSB (index 6), Pin 5 is MSB (index 3)
        # Reverse them to get proper binary: Pin5 Pin4 Pin3 Pin2
        magnitude_bits = pin_data[6] + pin_data[5] + pin_data[4] + pin_data[3]
        magnitude_value = int(magnitude_bits, 2) + 1  # 0-15 maps to 1-16

        # Pins 6-7 (indices 2,1) encode pump selection
        pin6 = pin_data[2]
        pin7 = pin_data[1]

        # Determine pump number
        if pin6 == '1' and pin7 == '0':
            pump_num = 1
        elif pin6 == '0' and pin7 == '1':
            pump_num = 2
        elif pin6 == '1' and pin7 == '1':
            pump_num = 3
        else:
            pump_num = None  # Invalid

        return magnitude_value, pump_num

    def update_pump_stats(self, pump_num, magnitude):
        """Update statistics for a specific pump"""
        if pump_num in self.pump_stats:
            self.pump_stats[pump_num]["triggers"] += 1
            self.pump_stats[pump_num]["total_units"] += magnitude

            # Update display
            self.pump_stat_labels[pump_num]["triggers"].config(
                text=str(self.pump_stats[pump_num]["triggers"]))
            self.pump_stat_labels[pump_num]["units"].config(
                text=str(self.pump_stats[pump_num]["total_units"]))

            # Calculate and update average
            triggers = self.pump_stats[pump_num]["triggers"]
            total = self.pump_stats[pump_num]["total_units"]
            avg = total / triggers if triggers > 0 else 0
            self.pump_stat_labels[pump_num]["average"].config(
                text=f"{avg:.2f}")

            # Update total delivered
            self.update_calculations(pump_num)

    def log_pump_activity(self, pump_num, magnitude, pin_data):
        """Log pump activity with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if pump_num is None:
            log_entry = f"[{timestamp}] INVALID - No pump selected (Pins: {pin_data})\n"
            color_tag = "invalid"
        else:
            desired = float(self.pump_stats[pump_num]["desired_unit_size"].get())
            delivered_per_unit = float(self.pump_stats[pump_num]["delivered_unit_size"].get())
            total_delivered = magnitude * delivered_per_unit

            # Show the magnitude bits in proper order for the log
            mag_bits = pin_data[6] + pin_data[5] + pin_data[4] + pin_data[3]

            log_entry = f"[{timestamp}] Pump {pump_num} - {magnitude} units - {total_delivered:.2f} µL (Binary: {mag_bits})\n"
            color_tag = f"pump{pump_num}"

        # Configure tags for colors
        self.log_area.tag_config("pump1", foreground="blue")
        self.log_area.tag_config("pump2", foreground="green")
        self.log_area.tag_config("pump3", foreground="purple")
        self.log_area.tag_config("invalid", foreground="red")

        # Insert with color tag
        self.log_area.insert(tk.END, log_entry, color_tag)

        if self.autoscroll_log_var.get():
            self.log_area.see(tk.END)

    def reset_all_stats(self):
        """Reset all pump statistics"""
        for pump_num in [1, 2, 3]:
            self.pump_stats[pump_num]["triggers"] = 0
            self.pump_stats[pump_num]["total_units"] = 0
            self.pump_stat_labels[pump_num]["triggers"].config(text="0")
            self.pump_stat_labels[pump_num]["units"].config(text="0")
            self.pump_stat_labels[pump_num]["average"].config(text="0.0")
            self.update_calculations(pump_num)

        self.log_area.insert(tk.END, f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Statistics reset\n")

    def export_stats_csv(self):
        """Export pump statistics to CSV file"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"pump_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )

        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(
                        "Pump,Triggers,Total Units,Average Units/Trigger,Desired Unit Size (µL),Delivered Unit Size (µL),Total Delivered (µL)\n")
                    for pump_num in [1, 2, 3]:
                        triggers = self.pump_stats[pump_num]["triggers"]
                        total = self.pump_stats[pump_num]["total_units"]
                        avg = total / triggers if triggers > 0 else 0
                        desired = self.pump_stats[pump_num]["desired_unit_size"].get()
                        delivered = self.pump_stats[pump_num]["delivered_unit_size"].get()
                        total_del = self.pump_stats[pump_num]["total_delivered"].get()
                        f.write(f"{pump_num},{triggers},{total},{avg:.2f},{desired},{delivered},{total_del}\n")
                self.log_area.insert(tk.END,
                                     f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Statistics exported to {filename}\n")
            except Exception as e:
                self.log_area.insert(tk.END, f"Error exporting stats: {str(e)}\n")

    def clear_log(self):
        """Clear the activity log"""
        self.log_area.delete(1.0, tk.END)

    def save_log(self):
        """Save activity log to file - User chooses location"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            initialfile=f"pump_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_area.get(1.0, tk.END))
                self.log_area.insert(tk.END,
                                     f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Log saved to {filename}\n")
            except Exception as e:
                self.log_area.insert(tk.END, f"Error saving log: {str(e)}\n")

    def auto_save_log_on_exit(self):
        """Automatically save log file when exiting"""
        log_content = self.log_area.get(1.0, tk.END).strip()

        if log_content:  # Only save if there's content
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = os.path.join(self.log_directory, f"pump_log_{timestamp}.txt")

            try:
                with open(filename, 'w') as f:
                    f.write("=" * 70 + "\n")
                    f.write(f"Pump Monitor Log - Session ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write("=" * 70 + "\n\n")

                    # Write pump parameters
                    f.write("PUMP PARAMETERS:\n")
                    f.write("-" * 70 + "\n")
                    for pump_num in [1, 2, 3]:
                        f.write(f"Pump {pump_num}:\n")
                        f.write(f"  Desired Unit Size: {self.pump_stats[pump_num]['desired_unit_size'].get()} µL\n")
                        f.write(f"  Delivered Unit Size: {self.pump_stats[pump_num]['delivered_unit_size'].get()} µL\n")
                        f.write(f"  Total Triggers: {self.pump_stats[pump_num]['triggers']}\n")
                        f.write(f"  Total Units: {self.pump_stats[pump_num]['total_units']}\n")
                        f.write(f"  Total Delivered: {self.pump_stats[pump_num]['total_delivered'].get()} µL\n\n")

                    f.write("=" * 70 + "\n")
                    f.write("ACTIVITY LOG:\n")
                    f.write("=" * 70 + "\n")
                    f.write(log_content)

                print(f"Log automatically saved to: {filename}")
                return True
            except Exception as e:
                print(f"Error auto-saving log: {str(e)}")
                return False
        return True

    def refresh_ports(self):
        """Refresh the list of available serial ports"""
        ports = serial.tools.list_ports.comports()
        port_list = [port.device for port in ports]
        self.port_combo['values'] = port_list
        if port_list:
            self.port_combo.current(0)

    def toggle_connection(self):
        """Connect or disconnect from the serial port"""
        if not self.is_connected:
            self.connect()
        else:
            self.disconnect()

    def connect(self):
        """Establish connection to Arduino"""
        try:
            port = self.port_combo.get()
            baud = int(self.baud_combo.get())

            if not port:
                self.log_area.insert(tk.END, "Error: No port selected\n")
                return

            self.serial_port = serial.Serial(port, baud, timeout=1)
            time.sleep(2)  # Wait for Arduino to reset

            self.is_connected = True
            self.connect_btn.config(text="Disconnect")
            self.status_label.config(text="Connected", foreground="green")
            self.port_combo.config(state="disabled")
            self.baud_combo.config(state="disabled")

            # Start reading thread
            self.reading_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.reading_thread.start()

            self.log_area.insert(tk.END, f"=== Connected to {port} at {baud} baud ===\n")

        except serial.SerialException as e:
            self.log_area.insert(tk.END, f"Error: {str(e)}\n")

    def disconnect(self):
        """Disconnect from Arduino"""
        self.is_connected = False

        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()

        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Disconnected", foreground="red")
        self.port_combo.config(state="readonly")
        self.baud_combo.config(state="readonly")

        self.log_area.insert(tk.END, "=== Disconnected ===\n")

        # Reset decoded displays
        self.current_magnitude.set("--")
        self.current_pump.set("None")
        self.current_binary.set("----")
        self.pump_label.config(fg="gray")

    def read_serial(self):
        """Read data from serial port in a separate thread"""
        while self.is_connected and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    data = self.serial_port.readline().decode('utf-8', errors='ignore').strip()

                    if data:
                        # Check if this is pin state data (7 digits of 0s and 1s)
                        if len(data) == 7 and all(c in '01' for c in data):
                            self.root.after(0, self.process_pump_data, data)

            except serial.SerialException:
                self.is_connected = False
                self.root.after(0, self.disconnect)
                break
            except Exception as e:
                self.log_area.insert(tk.END, f"Error reading: {str(e)}\n")

    def process_pump_data(self, pin_data):
        """Process and display decoded pump data"""
        # Decode magnitude and pump
        magnitude, pump_num = self.decode_pump_data(pin_data)

        # Update decoded display
        if magnitude is not None:
            self.current_magnitude.set(str(magnitude))
            # Show magnitude bits in correct order (Pin5 Pin4 Pin3 Pin2)
            self.current_binary.set(pin_data[6] + pin_data[5] + pin_data[4] + pin_data[3])
        else:
            self.current_magnitude.set("ERR")
            self.current_binary.set("ERR")

        if pump_num is not None:
            self.current_pump.set(f"Pump {pump_num}")
            self.pump_label.config(fg=self.get_pump_color(pump_num))

            # Update statistics
            self.update_pump_stats(pump_num, magnitude)
        else:
            self.current_pump.set("INVALID")
            self.pump_label.config(fg="red")

        # Log the activity
        self.log_pump_activity(pump_num, magnitude, pin_data)

        # Increment total counter and flash LED
        self.increment_counter()
        self.flash_trigger_led()

    def flash_trigger_led(self):
        """Flash the trigger LED from red to green momentarily"""
        # Turn LED green
        self.led_canvas.itemconfig(self.led_indicator, fill="lime green", outline="darkgreen")

        # Schedule return to red after 300ms
        self.root.after(300, lambda: self.led_canvas.itemconfig(
            self.led_indicator, fill="red", outline="darkred"))

    def increment_counter(self):
        """Increment the trigger counter"""
        self.trigger_count += 1
        self.trigger_count_var.set(str(self.trigger_count))

    def reset_counter(self):
        """Reset the trigger counter to 0"""
        self.trigger_count = 0
        self.trigger_count_var.set("0")
        self.log_area.insert(tk.END, f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Trigger counter reset to 0\n")

    def on_closing(self):
        """Handle window closing - auto-save log"""
        if self.is_connected:
            self.disconnect()

        # Auto-save log
        success = self.auto_save_log_on_exit()

        if success:
            self.root.destroy()
        else:
            response = messagebox.askyesno(
                "Save Error",
                "Failed to auto-save log. Exit anyway?")
            if response:
                self.root.destroy()


def main():
    root = tk.Tk()
    app = ArduinoSerialGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()