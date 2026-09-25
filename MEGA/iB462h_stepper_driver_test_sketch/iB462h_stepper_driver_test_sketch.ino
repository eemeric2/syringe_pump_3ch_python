// IB462H Stepper Driver Test Sketch
// Tests: 160 steps forward, 1 second pause, 160 steps reverse, repeat

// Pin definitions
const int ENABLE_PIN = 8;
const int STEP_PIN = 9;
const int DIR_PIN = 10;

// Timing constants
const int STEP_PULSE_WIDTH = 600;    // microseconds
const int STEP_INTERVAL = 600;       // microseconds (between pulses)
const int PAUSE_TIME = 1000;         // milliseconds (between directions)
 
const int n_steps = 320; 
void setup() {
  Serial.begin(9600);
  
  // Initialize pins
  pinMode(ENABLE_PIN, OUTPUT);
  pinMode(STEP_PIN, OUTPUT);
  pinMode(DIR_PIN, OUTPUT);
  
  // IB462H: HIGH = enabled, LOW = disabled
  digitalWrite(ENABLE_PIN, LOW);    // Disable driver
  digitalWrite(STEP_PIN, HIGH);      // Step idle state
  digitalWrite(DIR_PIN, LOW);        // Start with clockwise (forward)
  
  Serial.println("IB462H Test Sketch Started");
  Serial.println("160 steps forward, 1s pause, 160 steps reverse");
}

void loop() {
   
  // Forward direction (LOW)
  digitalWrite(DIR_PIN, LOW);
  Serial.println("Forward...");

  stepMotor(n_steps);
  

  delay(PAUSE_TIME);
  
  // Reverse direction (HIGH)
  digitalWrite(DIR_PIN, HIGH);
  Serial.println("Reverse...");
  stepMotor(n_steps);
  
  delay(PAUSE_TIME);
}

void stepMotor(int numSteps) {
  digitalWrite(ENABLE_PIN, LOW);    // Enable driver
  delay(25); 
  for (int i = 0; i < numSteps; i++) {
    // Active LOW pulse for IB462H
    digitalWrite(STEP_PIN, LOW);           // Falling edge = step occurs
    delayMicroseconds(STEP_PULSE_WIDTH);
    digitalWrite(STEP_PIN, HIGH);          // Return to idle
    delayMicroseconds(STEP_INTERVAL);
  }
  delay(10);
  digitalWrite(ENABLE_PIN, HIGH);    // Disable driver
 
  Serial.print("Completed ");
  Serial.print(numSteps);
  Serial.println(" steps");
}