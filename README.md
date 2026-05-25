Web-Based Real-Time Hand & Finger Tracker
    This project allows you to control a 5-finger robotic hand in real-time using a webcam and a standard web browser. It hosts a local web server on a MicroPython-compatible microcontroller (like a Raspberry Pi Pico W or ESP32), serves a webpage utilizing Google MediaPipe, tracks hand landmarks, and translates those movements directly into physical servo motions via a PCA9685 I2C servo driver.

⚠️ Note: Currently optimized and tested exclusively for Google Chrome due to WebGL/Webcam permissions and specific MediaPipe WebAssembly execution requirements.

Features
    Zero Software Installation: No local Python scripts or heavy machine learning models need to run on your PC. Everything runs right inside the browser via WebAssembly (WASM).
    3D Distance Tracking: Calculates finger "openness" based on 3D Euclidean distance between the wrist and the respective finger tips.
    High-Speed HTTP Pipeline: Uses micro-optimizations (like HTTP 204 No Content responses and standard browser Image pre-fetching requests) to send coordinates every 150ms.
    Static Network Configurations: Configured with a static IP layout.

Configuration & Setup
1. Create your secret.py
    Before flashing your microcontroller, you must create a file named secret.py in the root directory of your device. Copy and paste the template below and update it with your network credentials:
    Python
# secret.py
SSID = "wifi_name"
PASSWORD = "wifi_password"

# Static IP settings (Adjust to match your router's subnet)
STATIC_IP = ""
SUBNET_MASK = ""
GATEWAY = ""
DNS = ""

2. Servo Channel Map
If your servos are plugged into different pins on the PCA9685 board, modify the dictionary at the top of main.py:
Python
servo_channels = {
    'thumb': 9,   
    'index': 10,  
    'middle': 7, 
    'ring': 11,    
    'pinky': 8    
}
