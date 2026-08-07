import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
from datetime import datetime
import os
import json


class PumpMonitorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Arduino Pump Monitor")
        self.root.geometry("1000x900")

        self.serial_connection = None
        self.is_connected = False

        # Pump constants
        self.MM_PER_STEP = 0.04
        self.ML_PER_MM = 0.20
        self.UL_PER_STEP = self.MM_PER_STEP * self.ML_PER_MM * 1000  # Convert to µL
        self.MAX_TRAVEL_MM = 40.0

        # State file path
        self.state_dir = os.path.join(os.path.expanduser("~"), "PumpMonitorLogs")
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_file = os.path.join(self.state_dir, "pump_state.json")

        # Statistics tracking
        self.total_triggers = 0
        self.pump_stats = {
            1: {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),
                "delivered_unit_size": tk.StringVar(value="0.0"),
                "total_delivered": tk.StringVar(value="0.0"),
                "position_mm": 0.0,  # Current plunger position
                "direction": 1  # 1 = forward (0->40), -1 = reverse (40->0)
            },
            2: {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),
                "delivered_unit_size": tk.StringVar(value="0.0"),
                "total_delivered": tk.StringVar(value="0.0"),
                "position_mm": 0.0,
                "direction": 1
            },
            3: {
                "triggers": 0,
                "total_units": 0,
                "desired_unit_size": tk.StringVar(value="10.0"),
                "delivered_unit_size": tk.StringVar(value="0.0"),
                "total_delivered": tk.StringVar(value="0.0"),
                "position_mm": 0.0,
                "direction": 1
            }
        }

        self.pump_colors = {1: "#4444FF", 2: "#44AA44", 3: "#AA44AA"}

        # Load state before creating widgets
        self.load_state()

        self.create_widgets()
        self.update_all_pump_calculations()
        self.update_all_position_displays()

    def load_state(self):
        """Load pump positions and directions from state file"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                for pump_num in [1, 2, 3]:
                    pump_key = str(pump_num)
                    if pump_key in state:
                        self.pump_stats[pump_num]["position_mm"] = state[pump_key].get("position_mm", 0.0)
                        self.pump_stats[pump_num]["direction"] = state[pump_key].get("direction", 1)

                        # Load desired unit size if available
                        if "desired_unit_size" in state[pump_key]:
                            self.pump_stats[pump_num]["desired_unit_size"].set(
                                str(state[pump_key]["desired_unit_size"]))

                print(f"State loaded from {self.state_file}")
            except Exception as e:
                print(f"Error loading state file: {e}")
                # Continue with default values
        else:
            print(f"No state file found, using defaults")

    def save_state(self):
        """Save pump positions and directions to state file"""
        try:
            state = {}
            for pump_num in [1, 2, 3]:
                stats = self.pump_stats[pump_num]
                state[str(pump_num)] = {
                    "position_mm": stats["position_mm"],
                    "direction": stats["direction"],
                    "desired_unit_size": stats["desired_unit_size"].get()
                }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

            print(f"State saved to {self.state_file}")
        except Exception as e:
            print(f"Error saving state file: {e}")

    def update_all_position_displays(self):
        """Update all position displays from current state"""
        for pump_num in [1, 2, 3]:
            stats = self.pump_stats[pump_num]
            if "position_label" in stats:  # Check if widgets exist
                stats["position_label"].config(text=f"{stats['position_mm']:.2f}")
                direction_text = "→" if stats["direction"] == 1 else "←"
                stats["direction_label"].config(text=direction_text)
                progress_percent = (stats["position_mm"] / self.MAX_TRAVEL_MM) * 100
                stats["position_bar"]["value"] = progress_percent

    def calculate_discrete_volume(self, desired_ul):
        """Calculate smallest discrete volume >= desired volume"""
        try:
            desired = float(desired_ul)
            if desired <= 0:
                return 0.0

            # Calculate minimum number of steps needed
            steps_needed = desired / self.UL_PER_STEP
            steps_actual = int(steps_needed) if steps_needed == int(steps_needed) else int(steps_needed) + 1

            # Calculate actual delivered volume
            delivered = steps_actual * self.UL_PER_STEP
            return round(delivered, 3)
        except ValueError:
            return 0.0

    def update_plunger_position(self, pump_num, units):
        """Update plunger position based on delivered units"""
        stats = self.pump_stats[pump_num]

        # Calculate distance traveled for this trigger
        delivered_ul = float(stats["delivered_unit_size"].get())
        distance_mm = (delivered_ul / 1000) / self.ML_PER_MM  # Convert µL to mm

        # Update position based on direction
        new_position = stats["position_mm"] + (distance_mm * stats["direction"])

        # Check if we need to reverse direction
        if new_position >= self.MAX_TRAVEL_MM:
            stats["direction"] = -1
            new_position = self.MAX_TRAVEL_MM - (new_position - self.MAX_TRAVEL_MM)
            self.log_message(f"Pump {pump_num} reversed direction at {self.MAX_TRAVEL_MM} mm (now moving backward)",
                             f"pump{pump_num}")
        elif new_position <= 0:
            stats["direction"] = 1
            new_position = abs(new_position)
            self.log_message(f"Pump {pump_num} reversed direction at 0 mm (now moving forward)", f"pump{pump_num}")

        stats["position_mm"] = new_position

        # Update display
        stats["position_label"].config(text=f"{new_position:.2f}")
        direction_text = "→" if stats["direction"] == 1 else "←"
        stats["direction_label"].config(text=direction_text)

        # Update progress bar
        progress_percent = (new_position / self.MAX_TRAVEL_MM) * 100
        stats["position_bar"]["value"] = progress_percent

        # Save state after position update
        self.save_state()

    def reset_plunger_position(self, pump_num):
        """Reset plunger to home position"""
        stats = self.pump_stats[pump_num]
        stats["position_mm"] = 0.0
        stats["direction"] = 1
        stats["position_label"].config(text="0.00")
        stats["direction_label"].config(text="→")
        stats["position_bar"]["value"] = 0
        self.log_message(f"Pump {pump_num} plunger reset to home position", f"pump{pump_num}")
        self.save_state()

    def update_pump_calculation(self, pump_num):
        """Update delivered and total for a specific pump"""
        stats = self.pump_stats[pump_num]
        desired_str = stats["desired_unit_size"].get()

        delivered = self.calculate_discrete_volume(desired_str)
        stats["delivered_unit_size"].set(f"{delivered:.3f}")

        total = delivered * stats["total_units"]
        stats["total_delivered"].set(f"{total:.3f}")

        # Save state when desired unit size changes
        self.save_state()

    def update_all_pump_calculations(self):
        """Update all pump calculations"""
        for pump_num in [1, 2, 3]:
            self.update_pump_calculation(pump_num)

    def on_desired_change(self, pump_num, event=None):
        """Called when desired unit size changes"""
        self.update_pump_calculation(pump_num)
        return True

    def create_widgets(self):
        # Connection Frame
        conn_frame = tk.LabelFrame(self.root, text="Connection", padx=10, pady=10)
        conn_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(conn_frame, text="Port:").grid(row=0, column=0, sticky="w")
        self.port_combo = ttk.Combobox(conn_frame, width=15)
        self.port_combo.grid(row=0, column=1, padx=5)
        self.refresh_ports()

        tk.Button(conn_frame, text="Refresh", command=self.refresh_ports).grid(row=0, column=2, padx=5)

        tk.Label(conn_frame, text="Baud:").grid(row=0, column=3, padx=(20, 0))
        self.baud_combo = ttk.Combobox(conn_frame, width=10, values=["9600", "115200"])
        self.baud_combo.set("9600")
        self.baud_combo.grid(row=0, column=4, padx=5)

        self.connect_btn = tk.Button(conn_frame, text="Connect", command=self.toggle_connection, bg="lightgreen")
        self.connect_btn.grid(row=0, column=5, padx=10)

        # Status Frame
        status_frame = tk.LabelFrame(self.root, text="Current Status", padx=10, pady=10)
        status_frame.pack(fill="x", padx=10, pady=5)

        tk.Label(status_frame, text="Binary Code:").grid(row=0, column=0, sticky="w")
        self.binary_label = tk.Label(status_frame, text="- - - - - - -", font=("Courier", 14), fg="blue")
        self.binary_label.grid(row=0, column=1, padx=10, sticky="w")

        tk.Label(status_frame, text="Magnitude:").grid(row=1, column=0, sticky="w")
        self.magnitude_label = tk.Label(status_frame, text="--", font=("Arial", 14, "bold"))
        self.magnitude_label.grid(row=1, column=1, padx=10, sticky="w")

        tk.Label(status_frame, text="Active Pump:").grid(row=2, column=0, sticky="w")
        self.pump_label = tk.Label(status_frame, text="--", font=("Arial", 14, "bold"))
        self.pump_label.grid(row=2, column=1, padx=10, sticky="w")

        # Trigger indicator
        self.trigger_led = tk.Label(status_frame, text="●", font=("Arial", 24), fg="red")
        self.trigger_led.grid(row=0, column=2, rowspan=3, padx=20)

        # Total triggers
        tk.Label(status_frame, text="Total Triggers:").grid(row=0, column=3, sticky="w", padx=(20, 0))
        self.total_trigger_label = tk.Label(status_frame, text="0", font=("Arial", 14, "bold"))
        self.total_trigger_label.grid(row=0, column=4, padx=5, sticky="w")
        tk.Button(status_frame, text="Reset Stats", command=self.reset_fluid_stats).grid(row=0, column=5, padx=5)

        # Pump Statistics Frame (Table Format)
        stats_frame = tk.LabelFrame(self.root, text="Pump Statistics", padx=10, pady=10)
        stats_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Headers
        headers = ["Pump", "Triggers", "Total Units", "Avg Units", "Desired Unit (µL)", "Delivered Unit (µL)",
                   "Total Delivered (µL)"]
        for col, header in enumerate(headers):
            tk.Label(stats_frame, text=header, font=("Arial", 10, "bold")).grid(row=0, column=col, padx=5, pady=5,
                                                                                sticky="w")

        # Pump rows
        for pump_num in [1, 2, 3]:
            row = pump_num
            color = self.pump_colors[pump_num]
            stats = self.pump_stats[pump_num]

            # Pump number
            tk.Label(stats_frame, text=f"Pump {pump_num}", fg=color, font=("Arial", 10, "bold")).grid(row=row, column=0,
                                                                                                      padx=5, pady=2,
                                                                                                      sticky="w")

            # Triggers
            label = tk.Label(stats_frame, text="0", font=("Arial", 10))
            label.grid(row=row, column=1, padx=5, pady=2, sticky="w")
            stats["triggers_label"] = label

            # Total units
            label = tk.Label(stats_frame, text="0", font=("Arial", 10))
            label.grid(row=row, column=2, padx=5, pady=2, sticky="w")
            stats["total_units_label"] = label

            # Average units
            label = tk.Label(stats_frame, text="0.00", font=("Arial", 10))
            label.grid(row=row, column=3, padx=5, pady=2, sticky="w")
            stats["avg_units_label"] = label

            # Desired unit size (editable)
            entry = tk.Entry(stats_frame, textvariable=stats["desired_unit_size"], width=12)
            entry.grid(row=row, column=4, padx=5, pady=2, sticky="w")
            entry.bind("<Return>", lambda e, p=pump_num: self.on_desired_change(p))
            entry.bind("<FocusOut>", lambda e, p=pump_num: self.on_desired_change(p))

            # Delivered unit size (calculated)
            label = tk.Label(stats_frame, textvariable=stats["delivered_unit_size"], font=("Arial", 10))
            label.grid(row=row, column=5, padx=5, pady=2, sticky="w")

            # Total delivered (calculated)
            label = tk.Label(stats_frame, textvariable=stats["total_delivered"], font=("Arial", 10))
            label.grid(row=row, column=6, padx=5, pady=2, sticky="w")

        # Plunger Position Frame
        position_frame = tk.LabelFrame(self.root, text="Plunger Positions", padx=10, pady=10)
        position_frame.pack(fill="x", padx=10, pady=5)

        for pump_num in [1, 2, 3]:
            color = self.pump_colors[pump_num]
            stats = self.pump_stats[pump_num]

            # Create frame for each pump
            pump_frame = tk.Frame(position_frame)
            pump_frame.pack(fill="x", pady=5)

            # Pump label
            tk.Label(pump_frame, text=f"Pump {pump_num}:", fg=color, font=("Arial", 10, "bold"), width=8).pack(
                side="left", padx=5)

            # Direction indicator
            direction_label = tk.Label(pump_frame, text="→", font=("Arial", 14), fg=color)
            direction_label.pack(side="left", padx=5)
            stats["direction_label"] = direction_label

            # Position value
            position_label = tk.Label(pump_frame, text="0.00", font=("Arial", 11, "bold"))
            position_label.pack(side="left", padx=2)
            stats["position_label"] = position_label

            tk.Label(pump_frame, text="mm", font=("Arial", 10)).pack(side="left", padx=2)

            # Progress bar
            position_bar = ttk.Progressbar(pump_frame, length=300, mode='determinate', maximum=100)
            position_bar.pack(side="left", padx=10)
            stats["position_bar"] = position_bar

            # Range label
            tk.Label(pump_frame, text=f"(0-{self.MAX_TRAVEL_MM} mm)", font=("Arial", 9)).pack(side="left", padx=5)

            # Reset button
            tk.Button(pump_frame, text="Reset Position",
                      command=lambda p=pump_num: self.reset_plunger_position(p)).pack(side="left", padx=5)

        # Activity Log Frame
        log_frame = tk.LabelFrame(self.root, text="Activity Log", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True)

        # Configure tags for colors
        self.log_text.tag_config("pump1", foreground=self.pump_colors[1])
        self.log_text.tag_config("pump2", foreground=self.pump_colors[2])
        self.log_text.tag_config("pump3", foreground=self.pump_colors[3])
        self.log_text.tag_config("error", foreground="red")

        # Control Buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        tk.Button(btn_frame, text="Save Log", command=self.save_log).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Export Stats CSV", command=self.export_stats).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Clear Log", command=self.clear_log).pack(side="left", padx=5)

    def refresh_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.current(0)

    def toggle_connection(self):
        if not self.is_connected:
            try:
                port = self.port_combo.get()
                baud = int(self.baud_combo.get())
                self.serial_connection = serial.Serial(port, baud, timeout=1)
                self.is_connected = True
                self.connect_btn.config(text="Disconnect", bg="lightcoral")
                self.log_message(f"Connected to {port} at {baud} baud")
                self.read_serial()
            except Exception as e:
                messagebox.showerror("Connection Error", str(e))
        else:
            if self.serial_connection:
                self.serial_connection.close()
            self.is_connected = False
            self.connect_btn.config(text="Connect", bg="lightgreen")
            self.log_message("Disconnected")

    def read_serial(self):
        if self.is_connected and self.serial_connection and self.serial_connection.in_waiting:
            try:
                line = self.serial_connection.readline().decode('utf-8').strip()
                if line:
                    self.process_data(line)
            except Exception as e:
                self.log_message(f"Error reading serial: {e}", "error")

        if self.is_connected:
            self.root.after(50, self.read_serial)

    def process_data(self, data):
        # Expecting format like "1010101" (7 bits)
        # Silently ignore invalid data (like dashes or other noise)
        if len(data) == 7 and all(c in '01' for c in data):
            self.decode_pins(data)
        # else: silently ignore invalid/noise data

    def decode_pins(self, pin_data):
        # Format: Pin8 Pin7 Pin6 Pin5 Pin4 Pin3 Pin2
        # Index:  [0]  [1]  [2]  [3]  [4]  [5]  [6]

        # Update binary display
        formatted = ' '.join(pin_data)
        self.binary_label.config(text=formatted)

        # Decode magnitude (pins 2-5, indices 6,5,4,3)
        magnitude_bits = pin_data[6] + pin_data[5] + pin_data[4] + pin_data[3]
        magnitude_value = int(magnitude_bits, 2) + 1  # 0-15 → 1-16
        self.magnitude_label.config(text=str(magnitude_value))

        # Decode pump (pins 6-7, indices 2,1)
        pin6 = pin_data[2]
        pin7 = pin_data[1]

        if pin6 == '1' and pin7 == '0':
            pump_num = 1
        elif pin6 == '0' and pin7 == '1':
            pump_num = 2
        elif pin6 == '1' and pin7 == '1':
            pump_num = 3
        else:
            pump_num = None

        if pump_num:
            color = self.pump_colors[pump_num]
            self.pump_label.config(text=f"Pump {pump_num}", fg=color)
            self.flash_trigger()
            self.update_statistics(pump_num, magnitude_value)
            self.log_message(f"Pump {pump_num} triggered - {magnitude_value} units", f"pump{pump_num}")
        else:
            # Invalid pump state - log it since this is an actual decode issue
            self.pump_label.config(text="Invalid", fg="red")
            self.log_message(f"Invalid pump state (Pin6={pin6}, Pin7={pin7})", "error")

    def flash_trigger(self):
        self.trigger_led.config(fg="green")
        self.root.after(200, lambda: self.trigger_led.config(fg="red"))

    def update_statistics(self, pump_num, units):
        stats = self.pump_stats[pump_num]
        stats["triggers"] += 1
        stats["total_units"] += units

        self.total_triggers += 1
        self.total_trigger_label.config(text=str(self.total_triggers))

        # Update labels
        stats["triggers_label"].config(text=str(stats["triggers"]))
        stats["total_units_label"].config(text=str(stats["total_units"]))

        avg = stats["total_units"] / stats["triggers"] if stats["triggers"] > 0 else 0
        stats["avg_units_label"].config(text=f"{avg:.2f}")

        # Update volume calculations
        self.update_pump_calculation(pump_num)

        # Update plunger position
        self.update_plunger_position(pump_num, units)

    def reset_fluid_stats(self):
        """Reset fluid statistics (triggers, units, volumes) but NOT plunger positions"""
        if messagebox.askyesno("Reset Statistics",
                               "Reset triggers and fluid delivery statistics?\n(Plunger positions will NOT be reset)"):
            self.total_triggers = 0
            self.total_trigger_label.config(text="0")

            for pump_num in [1, 2, 3]:
                stats = self.pump_stats[pump_num]
                stats["triggers"] = 0
                stats["total_units"] = 0
                stats["triggers_label"].config(text="0")
                stats["total_units_label"].config(text="0")
                stats["avg_units_label"].config(text="0.00")
                self.update_pump_calculation(pump_num)

            self.log_message("Fluid statistics reset (plunger positions preserved)")

    def log_message(self, message, tag=None):
        timestamp = datetime.now().strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}\n"

        self.log_text.config(state="normal")
        if tag:
            self.log_text.insert("end", full_message, tag)
        else:
            self.log_text.insert("end", full_message)
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def clear_log(self):
        if messagebox.askyesno("Clear Log", "Clear activity log?"):
            self.log_text.config(state="normal")
            self.log_text.delete(1.0, "end")
            self.log_text.config(state="disabled")

    def save_log(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pump_log_{timestamp}.txt"
        filepath = os.path.join(self.state_dir, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                # Write pump parameters
                f.write("=== Pump Parameters ===\n")
                for pump_num in [1, 2, 3]:
                    stats = self.pump_stats[pump_num]
                    f.write(f"\nPump {pump_num}:\n")
                    f.write(f"  Desired Unit Size: {stats['desired_unit_size'].get()} uL\n")
                    f.write(f"  Delivered Unit Size: {stats['delivered_unit_size'].get()} uL\n")
                    f.write(f"  Total Delivered: {stats['total_delivered'].get()} uL\n")
                    f.write(f"  Triggers: {stats['triggers']}\n")
                    f.write(f"  Total Units: {stats['total_units']}\n")
                    avg = stats["total_units"] / stats["triggers"] if stats["triggers"] > 0 else 0
                    f.write(f"  Average Units/Trigger: {avg:.2f}\n")
                    f.write(f"  Plunger Position: {stats['position_mm']:.2f} mm\n")
                    direction_text = "Forward (0->40)" if stats["direction"] == 1 else "Reverse (40->0)"
                    f.write(f"  Direction: {direction_text}\n")

                f.write(f"\nTotal Triggers (all pumps): {self.total_triggers}\n")
                f.write(f"\nPump Constants:\n")
                f.write(f"  mm/step: {self.MM_PER_STEP}\n")
                f.write(f"  mL/mm: {self.ML_PER_MM}\n")
                f.write(f"  uL/step: {self.UL_PER_STEP}\n")
                f.write(f"  Max travel: {self.MAX_TRAVEL_MM} mm\n")

                # Write activity log
                f.write("\n\n=== Activity Log ===\n")
                f.write(self.log_text.get(1.0, "end"))

            self.log_message(f"Log saved to {filepath}")
            messagebox.showinfo("Success", f"Log saved to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def export_stats(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(
                        "Pump,Triggers,Total_Units,Avg_Units,Desired_Unit_uL,Delivered_Unit_uL,Total_Delivered_uL,Position_mm,Direction\n")
                    for pump_num in [1, 2, 3]:
                        stats = self.pump_stats[pump_num]
                        avg = stats["total_units"] / stats["triggers"] if stats["triggers"] > 0 else 0
                        direction_text = "Forward" if stats["direction"] == 1 else "Reverse"
                        f.write(f"{pump_num},{stats['triggers']},{stats['total_units']},{avg:.2f},")
                        f.write(f"{stats['desired_unit_size'].get()},{stats['delivered_unit_size'].get()},")
                        f.write(f"{stats['total_delivered'].get()},{stats['position_mm']:.2f},{direction_text}\n")

                messagebox.showinfo("Success", f"Statistics exported to:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Export Error", str(e))

    def on_closing(self):
        # Save state before closing
        self.save_state()

        # Auto-save log on exit
        self.save_log()

        if self.serial_connection and self.is_connected:
            self.serial_connection.close()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = PumpMonitorGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
