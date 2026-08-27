#ONLY WORKS IN GOOGLE CHROME (for now)

import tinyweb
import uasyncio
import network
import time
import ujson
import logging
from machine import Pin, I2C
import secret #gets wifi stuff from secret.py (not on github)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("handctrl")

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

min_servo_pulse = 150
max_servo_pulse = 600
diff_servo_pulse = max_servo_pulse - min_servo_pulse

#tuning variable for smoothing (0.05 = very slow/smooth, 1 = no smoothing)
SMOOTHING_FACTOR = 0.15

# Servo Variable Definitions
# Using nested Dicts because Dataclasses are not in MicroPython
# Note: relying on GIL to handle synchronization/resource sharing of fingers
fingers = { # other state vars - fully closed/open, P I D, previous curernt pos - current pos = rise (D)  running sum - (I)
    'thumb': {'servo_channel': 9, 'set_point': 0, 'curr_point': 0, 'OTHER_STATE_VARS': []}, ## replicate for fingers
    'index':  {'servo_channel': 10, 'set_point': 0, 'curr_point': 0},
    'middle': {'servo_channel': 7,  'set_point': 0, 'curr_point': 0},
    'ring':   {'servo_channel': 11, 'set_point': 0, 'curr_point': 0},
    'pinky':  {'servo_channel': 8,  'set_point': 0, 'curr_point': 0},
}

#bring website into memory
with open('index.html', 'r', encoding='utf-8') as f:
    HTML = f.read()

# Create the tinyweb app
app = tinyweb.webserver()

#c + v from old servo controller script
def init_i2c():
    global i2c
    try:
        i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=100000)
        i2c.writeto_mem(PCA9685_ADDRESS, MODE1, b'\x10') #
        time.sleep(0.01)
        prescale = int(25000000.0 / (4096 * 50) - 1)
        i2c.writeto_mem(PCA9685_ADDRESS, PRESCALE, bytes([prescale])) #
        time.sleep(0.01)
        i2c.writeto_mem(PCA9685_ADDRESS, MODE1, b'\x00') #
        time.sleep(0.01)
        i2c.writeto_mem(PCA9685_ADDRESS, MODE1, b'\xa0') #
        time.sleep(0.01)
        return True
    except Exception as e:
        log.error("Init Failed: %s", e)
        return False


def set_servo(channel, pulse):
    off = pulse
    try:
        i2c.writeto_mem(PCA9685_ADDRESS, LED0_ON_L + 4 * channel, b'\x00\x00')
        i2c.writeto_mem(PCA9685_ADDRESS, LED0_ON_L + 4 * channel + 2, bytes([off & 0xFF, off >> 8]))
    except Exception:
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

    log.info("Connected! http://%s", wlan.ifconfig()[0])


# Index page  same as the old "GET / " branch
@app.route('/')
async def index(request, response):
    await response.start_html()
    await response.send(HTML)


# Finger same URL/query-string shape as the old "GET /d?..."

@app.route('/d')
async def set_fingers(request, response):
    global fingers
    try:
        qs = request.query_string
        if qs:
            if isinstance(qs, bytes):
                qs = qs.decode()
            log.info(qs)
            for p in qs.split('&'):
                if '=' in p and not p.startswith('ts='): #doesnt get thumb cofused w timestanp
                    name, val = p.split('=') #finds the values
                    try:
                        fingers[name]['set_point'] = percent_to_pulse(int(val))
                    except (KeyError, ValueError) as e:
                        log.warning("Bad finger update '%s': %s", p, e)
    except Exception as e:
        log.error("Error parsing query string: %s", e)

    # Report back the current servo position (curr_point, after
    # the lerp smoothing).
    status = {}
    for name, data in fingers.items():
        pct = (data['curr_point'] - min_servo_pulse) / diff_servo_pulse * 100
        status[name] = round(max(0, min(100, pct)))

    response.add_header('Content-Type', 'text/html')
    await response._send_headers()
    await response.send(ujson.dumps(status))


# def servo_control(): ## code for servo control, global for last function call time (ts)
def servo_control():
    global fingers
    for name, data in fingers.items():
        target = data['set_point']
        current = data['curr_point']

        # Linear Interpolation (Lerp)
        if abs(target - current) > 1:
            current += (target - current) * SMOOTHING_FACTOR # Move a fraction of the distance towards the target point
            data['curr_point'] = current

            set_servo(data['servo_channel'], int(current)) # Send updated pulse to the PCA9685


async def servo_control_loop():
    while True:
        servo_control()
        await uasyncio.sleep_ms(20) # ~50Hz update rate for the lerp smoothing


def run():
    if not init_i2c():
        log.warning("PCA9685 init failed, continuing anyway")
    connect_wifi()

    uasyncio.create_task(servo_control_loop())

    log.info("Server live. Visit the IP above in Chrome.")
    app.run(host='0.0.0.0', port=80)


if __name__ == '__main__':
    run()
