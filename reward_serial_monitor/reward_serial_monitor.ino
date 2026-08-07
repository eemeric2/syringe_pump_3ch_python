// Define the starting and ending digital pins
const int START_PIN = 2;
const int END_PIN = 8;
const int TRIGGER = 9;

bool lastTriggerState = LOW;

void setup() {
  // Initialize serial communication at 9600 bits per second
  Serial.begin(9600);
  
  // Configure pins 2 through 9 as inputs with internal pull-up resistors
  for (int pin = START_PIN; pin <= END_PIN; pin++) {
    pinMode(pin, INPUT_PULLUP); 
  }
  pinMode(TRIGGER, INPUT_PULLUP);
}

void loop() {
  bool currentTriggerState = digitalRead(TRIGGER);
  
  // Check for rising edge (transition from LOW to HIGH)
  if (currentTriggerState == HIGH && lastTriggerState == LOW) {
    // Read and print the state of each pin
    for (int pin = START_PIN; pin <= END_PIN; pin++) {
      int pinState = digitalRead(pin);
      Serial.print(pinState);
    }
    Serial.println("");
    Serial.println("--------------");
    delay(50); // Debounce delay
  }
  
  lastTriggerState = currentTriggerState;
}