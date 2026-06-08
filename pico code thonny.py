#ONLY WORKS IN GOOGLE CHROME (for now) 
import network
import socket
import time
from machine import Pin, I2C
from collections import namedtuple
import secret #gets wifi stuff from secret.py (not on github)

# WiFi (hide) 
SSID = secret.SSID
PASSWORD = secret.PASSWORD

# Static IP settings
STATIC_IP = secret.STATIC_IP
SUBNET_MASK = secret.SUBNET_MASK
GATEWAY = secret.GATEWAY
DNS = secret.DNS

# PCA9685 Constants
PCA9685_ADDRESS = 0x40
MODE1 = 0x00
PRESCALE = 0xFE
LED0_ON_L = 0x06

# Servo Variable Definitions
# Using nested Dicts because Dataclasses are not in MicroPython
fingers = { # other state vars - fully closed/open, P I D, previous curernt pos - current pos = rise (D)  running sum - (I) 
    'thumb': {'servo_channel': 9, 'set_point': 0, 'curr_point': 0, 'OTHER_STATE_VARS': []}, ## replicate for fingers 
    'index': FingerData(10,0,0,0),  
    'middle': FingerData(7,0,0,0), 
    'ring': FingerData(11,0,0,0),    
    'pinky': FingerData(8,0,0,0),    
}
min_servo_pulse = 150
max_servo_pulse = 600
diff_servo_pulse = max_servo_pulse - min_servo_pulse

# same html but this time as a varialbe 
HTML = b"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hand Tracker - Inverted Logic</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background-color: #121212; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; overflow: hidden; }
        #liveView { position: relative; width: 640px; height: 480px; background: #000; border-radius: 10px; border: 4px solid #333; }
        #webcam, #output_canvas { position: absolute; left: 0; top: 0; width: 640px; height: 480px; transform: scaleX(-1); }
        #output_canvas { z-index: 5; pointer-events: none; }
        #ui-overlay { position: absolute; top: 10px; right: 10px; background: rgba(0, 0, 0, 0.8); padding: 15px; border-radius: 8px; border: 1px solid #444; z-index: 20; min-width: 150px; }
        .finger-row { display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 14px; }
        .percent-val { color: #00FF00; font-weight: bold; }
        .inverted { color: #FFA500; } /* Orange color for inverted fingers */
        #webcamButton { padding: 15px 30px; font-size: 18px; background-color: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; margin-bottom: 20px; z-index: 100; }
    </style>
</head>
<body>
    <h1>Independent Finger Tracking</h1>
    <button id="webcamButton">ENABLE WEBCAM</button>
    <div id="liveView">
        <div id="ui-overlay">
            <div class="finger-row">Thumb: <span id="thumb-val" class="percent-val">0%</span></div>
            <div class="finger-row">Index: <span id="index-val" class="percent-val">0%</span></div>
            <div class="finger-row">Middle: <span id="middle-val" class="percent-val">0%</span></div>
            <div class="finger-row">Ring: <span id="ring-val" class="percent-val">0%</span></div>
            <div class="finger-row">Pinky: <span id="pinky-val" class="percent-val">0%</span></div>
        </div>
        <video id="webcam" autoplay playsinline></video>
        <canvas id="output_canvas"></canvas>
    </div>
    <script type="module">
    
    // limit how often data gets sent to server
    
        import { HandLandmarker, FilesetResolver, DrawingUtils } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0";
        
        const video = document.getElementById("webcam");
        const canvasElement = document.getElementById("output_canvas");
        const canvasCtx = canvasElement.getContext("2d");
        const webcamButton = document.getElementById("webcamButton");
        const uiElements = {
            thumb: document.getElementById("thumb-val"),
            index: document.getElementById("index-val"),
            middle: document.getElementById("middle-val"),
            ring: document.getElementById("ring-val"),
            pinky: document.getElementById("pinky-val")
        };

        let handLandmarker;
        let lastVideoTime = -1;
        let lastSend = 0;

        // configuration for finger landmarks and distance scaling
        const fingerConfigs = {
            thumb:  { tip: 4,  min: 0.15, max: 0.45 },
            index:  { tip: 8,  min: 0.20, max: 0.70 },
            middle: { tip: 12, min: 0.20, max: 0.75 },
            ring:   { tip: 16, min: 0.20, max: 0.70 },
            pinky:  { tip: 20, min: 0.15, max: 0.60 }
        };

        // same proccess as old computer script 
        // these fingers will have their values flipped (100 -> 0)
        const REVERSE_VALS = ['thumb', 'index', 'ring'];

        async function createHandLandmarker() {
            const vision = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.0/wasm");
            handLandmarker = await HandLandmarker.createFromOptions(vision, {
                baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task", delegate: "GPU" },
                runningMode: "VIDEO", numHands: 1
            });
        }
        createHandLandmarker();

        webcamButton.addEventListener("click", async () => {
            webcamButton.style.display = "none";
            const stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
            video.addEventListener("loadeddata", () => {
                canvasElement.width = video.videoWidth;
                canvasElement.height = video.videoHeight;
                predictWebcam();
            });
        });

        function predictWebcam() {
            let now = performance.now();
            if (lastVideoTime !== video.currentTime && handLandmarker) {
                lastVideoTime = video.currentTime;
                const results = handLandmarker.detectForVideo(video, now);
                canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);

                if (results.landmarks && results.landmarks[0]) {
                    const landmarks = results.landmarks[0];
                    const wrist = landmarks[0];
                    const drawingUtils = new DrawingUtils(canvasCtx);
                    
                    drawingUtils.drawConnectors(landmarks, HandLandmarker.HAND_CONNECTIONS, { color: "#00FF00", lineWidth: 5 });
                    drawingUtils.drawLandmarks(landmarks, { color: "#FF0000", lineWidth: 1 });
                    //measures distances and converts it to percentages
                    let qs = "";
                    for (const [name, config] of Object.entries(fingerConfigs)) {
                        const dist = Math.sqrt(
                            Math.pow(wrist.x - landmarks[config.tip].x, 2) + 
                            Math.pow(wrist.y - landmarks[config.tip].y, 2) + 
                            Math.pow(wrist.z - landmarks[config.tip].z, 2)
                        );
                        
                        let openness = Math.min(Math.max((dist - config.min) / (config.max - config.min), 0), 1);
                        let percent = Math.round(openness * 100);

                        //apply reverse math 
                        if (REVERSE_VALS.includes(name)) {
                            percent = 100 - percent;
                        }

                        uiElements[name].innerText = percent + "%";
                        qs += name + "=" + percent + "&";
                    }

                    if (now - lastSend >= 150) {
                        lastSend = now;
                        new Image().src = "/d?" + qs + "ts=" + Math.floor(now);
                    }
                }
            }
            window.requestAnimationFrame(predictWebcam);
        }
    </script>
</body>
</html>"""

#c + v from old servo controller script 
def init_i2c():
    global i2c
    try:
        i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=100000)
        i2c.writeto_mem(PCA9685_ADDRESS, MODE1, b'\x10')
        time.sleep(0.01)
        prescale = int(25000000.0 / (4096 * 50) - 1)
        i2c.writeto_mem(PCA9685_ADDRESS, PRESCALE, bytes([prescale]))
        time.sleep(0.01)
        i2c.writeto_mem(PCA9685_ADDRESS, MODE1, b'\x00')
        time.sleep(0.01)
        i2c.writeto_mem(PCA9685_ADDRESS, MODE1, b'\xa0')
        time.sleep(0.01)
        return True
    except Exception as e:
        print(f"   Init Failed: {e}")
        return False

def set_servo(channel, pulse):
    off = pulse
    try:
        i2c.writeto_mem(PCA9685_ADDRESS, LED0_ON_L + 4 * channel, b'\x00\x00')
        i2c.writeto_mem(PCA9685_ADDRESS, LED0_ON_L + 4 * channel + 2, bytes([off & 0xFF, off >> 8]))
    except:
        pass

def percent_to_pulse(percent):
    # Maps 0-100% from browser to 150(min) - 600(max) servo pulse
    return int(min_servo_pulse + (percent / 100.0) * (diff_servo_pulse))

#same wifi script
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.ifconfig((STATIC_IP, SUBNET_MASK, GATEWAY, DNS))
    wlan.connect(SSID, PASSWORD)
    
    while not wlan.isconnected():
        time.sleep(0.5)
    print("   connected! http://{}".format(wlan.ifconfig()[0]))
    
    
def handle_web_requests(s):
    global fingers
    cl, addr = s.accept() #accepts connnections 
    try:
        cl.settimeout(0.1) #gives browser .1 seconds to send data (ensures no lagging) 
        request = cl.recv(1024).decode("utf-8")
        #serves website
        if "GET /d?" in request:
            cl.send("HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n")
            try:
                query = request.split(' ')[1].split('?')[1]
                parts = query.split('&')
                for p in parts:
                    if '=' in p and not p.startswith('ts='): #doesnt get thumb cofused w timestanp
                        name, val = p.split('=') #finds the values 
                        try:
                            fingers[name]['set_point'] = percent_to_pulse(int(val))
                        except KeyError:
                            pass
            except:
                pass
        elif "GET / " in request: #check GET vs SET or POST 
            cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: {}\r\nConnection: close\r\n\r\n".format(len(HTML)))
            cl.sendall(HTML) # gets the html file w the .js code init
    except Exception:
        pass
    finally:
        cl.close() #closes connections 

# def servo_control(): ##write code for servo control, global for last function call time (ts) 


def main():
    init_i2c() #wakes up servo driver 
    connect_wifi()
    
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('', 80)) #listens on port 80 (default for web browsers) 
    s.listen(2)

    print("server live. visit the IP in chrome.")

    while True:
        handle_web_requests(s)

if __name__ == "__main__":
    main()