/*
  ============================================================================
  3-Channel Syringe Pump Controller for Arduino Mega
  ============================================================================
  
  Monitors 8-bit GPIO input from external device (TDT/Plexon system):
    - Bits 0-3: Magnitude (0-15, representing 1-16 units)
    - Bit 4: Unused (reserved)
    - Bits 5-6: Pump selection (10=Pump1, 01=Pump2, 11=Pump3)
    - Bit 7: Trigger (rising edge triggers delivery)
  
  GPIO Pin Mapping (reading left to right, Pin 2 to Pin 9):
    Position:  0  1  2  3  4  5  6  7
    Pin:       2  3  4  5  6  7  8  9
               └──────┬──────┘  └─┬─┘  └─ Trigger
                    Amount      Pump
  
  Example encodings:
    Pump 1, Amount 1:  00000101 (binary) = 0x05 (hex)
    Pump 1, Amount 2:  10000101 (binary) = 0x85 (hex)
    Pump 2, Amount 1:  00000011 (binary) = 0x03 (hex)
    Pump 3, Amount 5:  00100111 (binary) = 0x27 (hex)
  
  
  Controls 3 stepper motors with auto-reversal at 0-40mm boundaries.
  Sends JSON messages to Raspberry Pi monitor via USB serial.
  
  Serial Commands (all start with ! and end with \r\n):
    !GetCurrentPosition [pump]\r\n        - Get position of pump (1-3)
    !SetCurrentPosition [pump] [pos]\r\n  - Set position in mm
    !GetUnitSize [pump]\r\n               - Get unit size in µL
    !SetUnitSize [pump] [size]\r\n        - Set unit size in µL
    !Translate [pump] [distance]\r\n      - Move ±distance in mm
    !ManualReward [pump]\r\n              - Deliver one unit manually
    !SetCalibration [pump] [ppm]\r\n      - Set pulses per mm (default 945)FV
    !Home [pump]\r\n                      - Move to position 0
    !ResetCounter [pump]\r\n              - Reset trigger counter
    !GetStatus\r\n                        - Get full system status

  Hardware:
    - Input pins: 2-9 (GPIO bits 0-7)
    - Pump 1: EN=45, STEP=46, DIR=47
    - Pump 2: EN=48, STEP=49, DIR=50
    - Pump 3: EN=51, STEP=52, DIR=53
    - LED: Pin 13 (built-in)
  
  ============================================================================
*/

// ============================================================================
// CONSTANTS AND PIN DEFINITIONS
// ============================================================================

#define NUM_PUMPS 3
#define NUM_GPIO_BITS 8
#define TRIGGER_BIT_INDEX 7

// ============================================================================
// FORWARD DECLARATIONS
// ============================================================================

void CheckTrigger();
void ProcessSerialCommands();
void ProcessCommand(String cmd);
void DecodeTrigger(byte value, String binaryStr);
void DeliverReward(int pumpIndex, int units);
void ManualRewardFunc(int pumpIndex);
void TranslateFunc(int pumpIndex, float distanceMM);
void HomeFunc(int pumpIndex);
void SendTriggerJSON(int pumpNum, int magnitude, String binary);
void SendCompleteJSON(int pumpNum, float volume, float position, bool reversed);
void SendError(String message);
void SendWarning(String message);
void Cmd_GetCurrentPosition(String params);
void Cmd_SetCurrentPosition(String params);
void Cmd_GetUnitSize(String params);
void Cmd_SetUnitSize(String params);
void Cmd_Translate(String params);
void Cmd_ManualReward(String params);
void Cmd_SetCalibration(String params);
void Cmd_Home(String params);
void Cmd_ResetCounter(String params);
void Cmd_GetStatus(String params);
void Cmd_ManualTrigger(String params);
void Cmd_TestDirection(String params);
void Cmd_SetDirection(String params);

// GPIO input pins (TDT configuration)
//const int GPIO_PINS[NUM_GPIO_BITS] = {22, 23, 24, 25, 26, 27, 28, 29};
// different MEGA used than the one currently in the rig
const int GPIO_PINS[NUM_GPIO_BITS] = {2,3,4,5,6,7,8,9};
const int TRIGGER_PIN = 9; // Bit 7
unsigned long droppedTriggers = 0;
// for variability testing
unsigned long lastTriggerTime = 0;
unsigned long firstStepTime = 0;

// Stepper motor pins [pump_index][0=enable, 1=step, 2=direction]
const int STEPPER_PINS[NUM_PUMPS][3] = {
  {45, 46, 47},  // Pump 1
  {48, 49, 50},  // Pump 2
  {51, 52, 53}   // Pump 3
};

const int LED_PIN = LED_BUILTIN;

// Mechanical parameters
const float TOTAL_TRAVEL_MM = 40.0;
const float TOTAL_VOLUME_UL = 6600.0; // 6.6 mL
// 200 full steps/revolution
// stepper motor driver hardware configured for half-steps -> 400 steps/revolution 
// Calibration: 400 steps/rev ÷ 1.25mm pitch = 320 pulses/mm 
const unsigned long DEFAULT_PULSES_PER_MM = 320;

// Stepper timing (microseconds)
const int STEP_PULSE_WIDTH = 600;
const int INTER_PULSE_INTERVAL = 600;

// ============================================================================
// GLOBAL VARIABLES
// ============================================================================

// Per-pump state
struct PumpState {
  float currentPosition;        // mm (0-40)
  float unitSize;              // µL per unit
  unsigned long pulsesPerMM;   // Calibration parameter
  int pulseCount;              // Total pulses from home
  bool directionFlag;          // false=Forward(RIGHT), true=Reverse(LEFT)
  int triggerCount;            // Number of triggers received
  float totalVolumeDelivered;  // µL
};

PumpState pumps[NUM_PUMPS];

// Trigger detection
int triggerState = LOW;
byte gpioState[NUM_GPIO_BITS] = {0};

// Serial command buffer
String commandBuffer = "";

// ============================================================================
// SETUP
// ============================================================================

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for serial connection
  }
  
  // Print startup banner
  Serial.println(F("{\"type\":\"status\",\"message\":\"3-Channel Syringe Pump Controller Started\"}"));
  
  // Initialize GPIO pins
  pinMode(LED_PIN, OUTPUT);
  pinMode(TRIGGER_PIN, INPUT);
  for (int i = 0; i < NUM_GPIO_BITS; i++) {
    pinMode(GPIO_PINS[i], INPUT);
  }
  
  // Initialize stepper pins
  // Enables/disables the output section of the driver. When in
  // a logic HIGH state (not connected) the driver outputs are
  // enabled. Sinking this input will disable the driver outputs
  for (int pump = 0; pump < NUM_PUMPS; pump++) {
    pinMode(STEPPER_PINS[pump][0], OUTPUT); // Enable
    pinMode(STEPPER_PINS[pump][1], OUTPUT); // Step
    pinMode(STEPPER_PINS[pump][2], OUTPUT); // Direction
    digitalWrite(STEPPER_PINS[pump][0], HIGH); // Disable driver by default (HIGH = disabled)
    digitalWrite(STEPPER_PINS[pump][1], HIGH); // Step triggered by falling edge logic so initialize to HIGH
  }
  
  // Initialize pump states
  for (int i = 0; i < NUM_PUMPS; i++) {
    pumps[i].currentPosition = 0.0;
    pumps[i].unitSize = 60.0; // 60 µL default
    pumps[i].pulsesPerMM = DEFAULT_PULSES_PER_MM;
    pumps[i].pulseCount = 0;
    pumps[i].directionFlag = false; // Start going forward
    pumps[i].triggerCount = 0;
    pumps[i].totalVolumeDelivered = 0.0;
  }
  
  Serial.println(F("{\"type\":\"status\",\"message\":\"Initialization complete. Ready for triggers.\"}"));
}

// ============================================================================
// MAIN LOOP
// ============================================================================

void loop() {
  // Process serial commands
  ProcessSerialCommands();
  
  // Check for triggers
  CheckTrigger();
}

// ============================================================================
// SERIAL COMMAND PROCESSING
// ============================================================================

void ProcessSerialCommands() {
  while (Serial.available() > 0) {
    char c = Serial.read();
    
    if (c == '\n' || c == '\r') {
      if (commandBuffer.length() > 0) {
        ProcessCommand(commandBuffer);
        commandBuffer = "";
      }
    } else {
      commandBuffer += c;
    }
  }
}

void ProcessCommand(String cmd) {
  cmd.trim();
  
  // Remove leading '!' if present
  if (cmd.startsWith("!")) {
    cmd = cmd.substring(1);
  }
  
  // Parse command and parameters
  int spaceIndex = cmd.indexOf(' ');
  String command = "";
  String params = "";
  
  if (spaceIndex > 0) {
    command = cmd.substring(0, spaceIndex);
    params = cmd.substring(spaceIndex + 1);
  } else {
    command = cmd;
  }
  
  command.trim();
  params.trim();
  
  // Route to appropriate handler
  if (command.equalsIgnoreCase("GetCurrentPosition")) {
    Cmd_GetCurrentPosition(params);
  } else if (command.equalsIgnoreCase("SetCurrentPosition")) {
    Cmd_SetCurrentPosition(params);
  } else if (command.equalsIgnoreCase("GetUnitSize")) {
    Cmd_GetUnitSize(params);
  } else if (command.equalsIgnoreCase("SetUnitSize")) {
    Cmd_SetUnitSize(params);
  } else if (command.equalsIgnoreCase("Translate")) {
    Cmd_Translate(params);
  } else if (command.equalsIgnoreCase("ManualReward")) {
    Cmd_ManualReward(params);
  } else if (command.equalsIgnoreCase("SetCalibration")) {
    Cmd_SetCalibration(params);
  } else if (command.equalsIgnoreCase("Home")) {
    Cmd_Home(params);
  } else if (command.equalsIgnoreCase("ResetCounter")) {
    Cmd_ResetCounter(params);
  } else if (command.equalsIgnoreCase("GetStatus")) {
    Cmd_GetStatus(params);
  } else if (command.equalsIgnoreCase("ManualTrigger")) {
    Cmd_ManualTrigger(params);
  } else if (command.equalsIgnoreCase("TestDirection")) {
    Cmd_TestDirection(params);
  } else if (command.equalsIgnoreCase("SetDirection")) {
    Cmd_SetDirection(params);
  } else {
    SendError("Unknown command: " + command);
  }
}

// Helper function to parse integer from string
int ParseInt(String &str, int defaultValue) {
  str.trim();
  if (str.length() == 0) return defaultValue;
  return str.toInt();
}

// Helper function to parse float from string
float ParseFloat(String &str, float defaultValue) {
  str.trim();
  if (str.length() == 0) return defaultValue;
  return str.toFloat();
}

// Helper to extract first parameter
String GetFirstParam(String &params) {
  int spaceIndex = params.indexOf(' ');
  if (spaceIndex > 0) {
    return params.substring(0, spaceIndex);
  }
  return params;
}

// Helper to extract second parameter
String GetSecondParam(String &params) {
  int spaceIndex = params.indexOf(' ');
  if (spaceIndex > 0) {
    return params.substring(spaceIndex + 1);
  }
  return "";
}

// ============================================================================
// TRIGGER DETECTION AND DECODING
// ============================================================================

void CheckTrigger() {
  // Detect rising edge on trigger pin
  if (digitalRead(TRIGGER_PIN) == HIGH && triggerState == LOW) {
    triggerState = HIGH;
    digitalWrite(LED_PIN, HIGH);
    
    // Read all GPIO bits and build binary string (for logging)
    String binaryStr = "";
    byte value = 0;
    
    for (int i = 0; i < NUM_GPIO_BITS - 1; i++) {  // -1 to exclude trigger bit
      int bit = digitalRead(GPIO_PINS[i]);
      binaryStr += String(bit);
      value |= (bit << i);  // Directly place bit at correct position
    }
    
    // Decode the value
    DecodeTrigger(value, binaryStr);
    
    digitalWrite(LED_PIN, LOW);
  }
  
  // Detect falling edge
  if (digitalRead(TRIGGER_PIN) == LOW && triggerState == HIGH) {
    triggerState = LOW;
  }
}

void DecodeTrigger(byte value, String binaryStr) {
  // Debug: print the raw byte value and binary string
  // Serial.print(F("{\"type\":\"debug\",\"byte_value\":"));
  // Serial.print(value, BIN);
  // Serial.print(F(",\"binary_str\":\""));
  // Serial.print(binaryStr);
  // Serial.print(F("\",\"bits_0_3\":"));
  // Serial.print(value & 0x0F);
  // Serial.print(F(",\"bits_5_6\":"));
  // Serial.print((value >> 5) & 0x03, BIN);
  // Serial.println(F("}"));
  
  lastTriggerTime = micros();  // Record trigger time
  // Extract amount (bits 0-3)
  int amount = (value & 0x0F) + 1;  // 1-16
  
  // Extract pump (bits 5-6)
  int pump_code = (value >> 5) & 0x03;
  
  
  // Extract pump from pins 7-8 (indices 5-6 of binaryStr)
  String pump_bits = binaryStr.substring(5, 7);  // Get "10", "01", or "11"
  int pumpNum;

  if (pump_bits == "10") pumpNum = 1;
  else if (pump_bits == "01") pumpNum = 2;
  else if (pump_bits == "11") pumpNum = 3;
  else {
    SendError("Invalid pump number decoded from external signal");
    return;
  }
  
  if (amount < 1 || amount > 16) {
    SendError("Invalid amount decoded from external signal");
    return;
  }
  
  // DEBUG
  Serial.print(F("{\"type\":\"debug\",\"source\":\"MATLAB\",\"pump\":"));
  Serial.print(pumpNum);
  Serial.print(F(",\"amount\":"));
  Serial.print(amount);
  Serial.println(F("}"));

  int pumpIndex = pumpNum - 1;
  SendTriggerJSON(pumpNum, amount, binaryStr);
  DeliverReward(pumpIndex, amount);
}

// ============================================================================
// REWARD DELIVERY
// ============================================================================

void DeliverReward(int pumpIndex, int units) {
  PumpState &pump = pumps[pumpIndex];
  
  // Calculate volume and pulses
  float volumeToDeliver = units * pump.unitSize; // µL
  float distanceMM = volumeToDeliver / (TOTAL_VOLUME_UL / TOTAL_TRAVEL_MM);
  int pulsesToDeliver = round(distanceMM * pump.pulsesPerMM);
  
  // Check boundaries and reverse if necessary
  float newPosition;
  if (pump.directionFlag == false) { // Going forward
    newPosition = pump.currentPosition + distanceMM;
    if (newPosition > TOTAL_TRAVEL_MM) {
      pump.directionFlag = true; // Reverse
      newPosition = TOTAL_TRAVEL_MM - distanceMM;
    }
  } else { // Going reverse
    newPosition = pump.currentPosition - distanceMM;
    if (newPosition < 0) {
      pump.directionFlag = false; // Forward
      newPosition = 0 + distanceMM;
    }
  }
  
  // Enable motor
  digitalWrite(STEPPER_PINS[pumpIndex][0], LOW);
  delay(10);
  
  // Set direction
  if (pump.directionFlag == false) {
    digitalWrite(STEPPER_PINS[pumpIndex][2], HIGH); // Forward
  } else {
    digitalWrite(STEPPER_PINS[pumpIndex][2], LOW); // Reverse
  }
  
  // Record time just before first step
  firstStepTime = micros();
  unsigned long latency_us = firstStepTime - lastTriggerTime;
  
  Serial.print(F("{\"type\":\"debug\",\"latency_us\":"));
  Serial.print(latency_us);
  Serial.println(F("}"));

  // Send step pulses
  for (int i = 0; i < pulsesToDeliver; i++) {
    digitalWrite(STEPPER_PINS[pumpIndex][1], LOW);
    delayMicroseconds(STEP_PULSE_WIDTH);
    digitalWrite(STEPPER_PINS[pumpIndex][1], HIGH);
    delayMicroseconds(INTER_PULSE_INTERVAL);
  }
  
  // Update state
  pump.currentPosition = newPosition;
  pump.totalVolumeDelivered += volumeToDeliver;
  pump.triggerCount++;
  
  // Disable motor
  delay(25);
  digitalWrite(STEPPER_PINS[pumpIndex][0], HIGH);
  
  // Send completion JSON
  SendCompleteJSON(pumpIndex + 1, volumeToDeliver, pump.currentPosition, pump.directionFlag);
}
// ============================================================================
// MANUAL CONTROL FUNCTIONS
// ============================================================================

void ManualRewardFunc(int pumpIndex) {
  if (pumpIndex < 0 || pumpIndex >= NUM_PUMPS) {
    SendError("Invalid pump index for manual reward");
    return;
  }
  
  DeliverReward(pumpIndex, 1); // Deliver 1 unit
}

void TranslateFunc(int pumpIndex, float distanceMM) {
  if (pumpIndex < 0 || pumpIndex >= NUM_PUMPS) {
    SendError("Invalid pump index for translate");
    return;
  }
  
  PumpState &pump = pumps[pumpIndex];
  
  // Calculate target position
  float targetPosition = pump.currentPosition + distanceMM;
  
  // Clamp to valid range
  if (targetPosition < 0) targetPosition = 0;
  if (targetPosition > TOTAL_TRAVEL_MM) targetPosition = TOTAL_TRAVEL_MM;
  
  float actualDistance = targetPosition - pump.currentPosition;
  int pulsesToDeliver = abs(round(actualDistance * pump.pulsesPerMM));
  
  // Enable motor
  digitalWrite(STEPPER_PINS[pumpIndex][0], LOW);
  delay(25);
  
  // Set direction
  if (actualDistance >= 0) {
    digitalWrite(STEPPER_PINS[pumpIndex][2], HIGH); // Forward 
    pump.directionFlag = false;
  } else {
    digitalWrite(STEPPER_PINS[pumpIndex][2], LOW); // Reverse
    pump.directionFlag = true;
  }
  
  // Send step pulses (ACTIVE LOW - falling edge)
  digitalWrite(LED_PIN, HIGH);
  for (int i = 0; i < pulsesToDeliver; i++) {
    digitalWrite(STEPPER_PINS[pumpIndex][1], LOW); // Falling edge = step
    delayMicroseconds(STEP_PULSE_WIDTH);
    digitalWrite(STEPPER_PINS[pumpIndex][1], HIGH); // Return to idle
    delayMicroseconds(INTER_PULSE_INTERVAL);
  }
  digitalWrite(LED_PIN, LOW);
  
  // Update position
  pump.currentPosition = targetPosition;
  
  // Disable motor
  delay(10);
  digitalWrite(STEPPER_PINS[pumpIndex][0], HIGH);
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pumpIndex + 1);
  Serial.print(F(",\"message\":\"Translated to "));
  Serial.print(pump.currentPosition, 3);
  Serial.println(F(" mm\"}"));
}

void HomeFunc(int pumpIndex) {
  if (pumpIndex < 0 || pumpIndex >= NUM_PUMPS) {
    SendError("Invalid pump index for home");
    return;
  }
  
  TranslateFunc(pumpIndex, -pumps[pumpIndex].currentPosition);
}

// ============================================================================
// JSON OUTPUT FUNCTIONS
// ============================================================================

void SendTriggerJSON(int pumpNum, int magnitude, String binary) {
  PumpState &pump = pumps[pumpNum - 1];
  float volume = magnitude * pump.unitSize;
  char direction = pump.directionFlag ? 'R' : 'F';
  
  Serial.print(F("{\"type\":\"trigger\",\"pump\":"));
  Serial.print(pumpNum);
  Serial.print(F(",\"magnitude\":"));
  Serial.print(magnitude);
  Serial.print(F(",\"volume\":"));
  Serial.print(volume, 1);
  Serial.print(F(",\"position\":"));
  Serial.print(pump.currentPosition, 3);
  Serial.print(F(",\"direction\":\""));
  Serial.print(direction);
  Serial.print(F("\",\"binary\":\""));
  Serial.print(binary);
  Serial.println(F("\"}"));
}

void SendCompleteJSON(int pumpNum, float volume, float position, bool reversed) {
  char direction = reversed ? 'R' : 'F';
  
  Serial.print(F("{\"type\":\"complete\",\"pump\":"));
  Serial.print(pumpNum);
  Serial.print(F(",\"volume\":"));
  Serial.print(volume, 1);
  Serial.print(F(",\"position\":"));
  Serial.print(position, 3);
  Serial.print(F(",\"direction\":\""));
  Serial.print(direction);
  Serial.println(F("\"}"));
}

void SendError(String message) {
  Serial.print(F("{\"type\":\"error\",\"message\":\""));
  Serial.print(message);
  Serial.println(F("\"}"));
}

// ============================================================================
// SERIAL COMMAND HANDLERS
// ============================================================================

void Cmd_GetCurrentPosition(String params) {
  int pump = ParseInt(params, 1);
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.print(F(",\"position\":"));
  Serial.print(pumps[pump - 1].currentPosition, 3);
  Serial.println(F("}"));
}

void Cmd_SetCurrentPosition(String params) {
  String pumpStr = GetFirstParam(params);
  String posStr = GetSecondParam(params);
  
  int pump = ParseInt(pumpStr, 1);
  float position = ParseFloat(posStr, 0.0);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  if (position < 0 || position > TOTAL_TRAVEL_MM) {
    SendError("Position out of range (0-40mm)");
    return;
  }
  
  pumps[pump - 1].currentPosition = position;
  pumps[pump - 1].pulseCount = round(position * pumps[pump - 1].pulsesPerMM);
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.print(F(",\"message\":\"Position set to "));
  Serial.print(position, 3);
  Serial.println(F(" mm\"}"));
}

void Cmd_GetUnitSize(String params) {
  int pump = ParseInt(params, 1);
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.print(F(",\"unitSize\":"));
  Serial.print(pumps[pump - 1].unitSize, 1);
  Serial.println(F("}"));
}

void Cmd_SetUnitSize(String params) {
  String pumpStr = GetFirstParam(params);
  String sizeStr = GetSecondParam(params);
  
  int pump = ParseInt(pumpStr, 1);
  float size = ParseFloat(sizeStr, 30.0);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  pumps[pump - 1].unitSize = size;
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.print(F(",\"message\":\"Unit size set to "));
  Serial.print(size, 1);
  Serial.println(F(" µL\"}"));
}

void Cmd_Translate(String params) {
  String pumpStr = GetFirstParam(params);
  String distStr = GetSecondParam(params);
  
  int pump = ParseInt(pumpStr, 1);
  float distance = ParseFloat(distStr, 0.0);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  TranslateFunc(pump - 1, distance);
}

void Cmd_ManualReward(String params) {
  int pump = ParseInt(params, 1);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  ManualRewardFunc(pump - 1);
}

void Cmd_SetCalibration(String params) {
  String pumpStr = GetFirstParam(params);
  String ppmStr = GetSecondParam(params);
  
  int pump = ParseInt(pumpStr, 1);
  unsigned long ppm = (unsigned long)ParseInt(ppmStr, (int)DEFAULT_PULSES_PER_MM);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  pumps[pump - 1].pulsesPerMM = ppm;
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.print(F(",\"message\":\"Calibration set to "));
  Serial.print(ppm);
  Serial.println(F(" pulses/mm\"}"));
}

void Cmd_ManualTrigger(String params) {
  String pumpStr = GetFirstParam(params);
  String amountStr = GetSecondParam(params);
  
  int pump = ParseInt(pumpStr, 1);
  int amount = ParseInt(amountStr, 1);
  
  if (pump < 1 || pump > NUM_PUMPS || amount < 1 || amount > 16) {
    SendError("Invalid pump or amount");
    return;
  }
  
  SendTriggerJSON(pump, amount, "manual_command");
  DeliverReward(pump - 1, amount);
}
void Cmd_TestDirection(String params) {
  int pump = ParseInt(params, 1);
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump");
    return;
  }
  
  // Toggle direction pin 5 times to test
  for (int i = 0; i < 5; i++) {
    digitalWrite(STEPPER_PINS[pump-1][2], HIGH);
    delay(500);
    digitalWrite(STEPPER_PINS[pump-1][2], LOW);
    delay(500);
  }
  
  Serial.println(F("{\"type\":\"status\",\"message\":\"Direction pin test complete\"}"));
}
void Cmd_Home(String params) {
  int pump = ParseInt(params, 1);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  HomeFunc(pump - 1);
}

void Cmd_ResetCounter(String params) {
  int pump = ParseInt(params, 1);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  pumps[pump - 1].triggerCount = 0;
  pumps[pump - 1].totalVolumeDelivered = 0.0;
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.println(F(",\"message\":\"Counter reset\"}"));
}

void Cmd_GetStatus(String params) {
  Serial.println(F("{\"type\":\"status\",\"pumps\":["));
  
  for (int i = 0; i < NUM_PUMPS; i++) {
    Serial.print(F("  {\"pump\":"));
    Serial.print(i + 1);
    Serial.print(F(",\"position\":"));
    Serial.print(pumps[i].currentPosition, 3);
    Serial.print(F(",\"direction\":\""));
    Serial.print(pumps[i].directionFlag ? "R" : "F");
    Serial.print(F("\",\"unitSize\":"));
    Serial.print(pumps[i].unitSize, 1);
    Serial.print(F(",\"triggers\":"));
    Serial.print(pumps[i].triggerCount);
    Serial.print(F(",\"totalVolume\":"));
    Serial.print(pumps[i].totalVolumeDelivered, 1);
    Serial.print(F(",\"calibration\":"));
    Serial.print(pumps[i].pulsesPerMM);
    Serial.print(F("}"));
    if (i < NUM_PUMPS - 1) Serial.println(F(","));
  }
  
  Serial.println(F("]}"));
}

void Cmd_SetDirection(String params) {
  String pumpStr = GetFirstParam(params);
  String dirStr = GetSecondParam(params);
  
  int pump = ParseInt(pumpStr, 1);
  
  if (pump < 1 || pump > NUM_PUMPS) {
    SendError("Invalid pump number");
    return;
  }
  
  dirStr.toLowerCase();
  
  if (dirStr == "f" || dirStr == "forward") {
    pumps[pump - 1].directionFlag = false;
  } else if (dirStr == "r" || dirStr == "reverse") {
    pumps[pump - 1].directionFlag = true;
  } else {
    SendError("Invalid direction - use 'F'/'Forward' or 'R'/'Reverse'");
    return;
  }
  
  Serial.print(F("{\"type\":\"status\",\"pump\":"));
  Serial.print(pump);
  Serial.print(F(",\"message\":\"Direction set to "));
  Serial.print(dirStr);
  Serial.println(F("\"}"));
}

