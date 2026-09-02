#ONLY WORKS IN GOOGLE CHROME (for now)

##settings near the top, encapsulate concepts in classes, pass settings into class init's but store constants in --done

## restructure fingers + related concepts (i2c, lerp, fingers dict, control) in a class --done 
## restructure network/wifi --done 
## restructure tinyweb server app including app.route --dobe 
## dont use globals with classes, pass in by reference --done 
## __init isnt necessary, define them as constants within the class --done 

import tinyweb
import uasyncio
import network
import time
import ujson
import logging
from machine import Pin, I2C
import secret #gets wifi stuff from secret.py (not on github)

logging.basicConfig(level=logging.INFO) # set to info if not testing (debug while testing)
#if logging level is greater than info, do print and delete for ui looking thing
log = logging.getLogger("handctrl")


class HandController:
    # PCA9685 Constants
    MODE1 = 0x00 ##constant ##dont pass into init
    PRESCALE = 0xFE ##constant ## dont pass into init
    LED0_ON_L = 0x06 ##constant  ## dont pass into init

    min_servo_pulse = 150
    max_servo_pulse = 600
    diff_servo_pulse = max_servo_pulse - min_servo_pulse

    #tuning variable for smoothing (0.05 = very slow/smooth, 1 = no smoothing)
    SMOOTHING_FACTOR = 0.15

    def __init__(self, pca9685_address=0x40): ## may change (not constant) ## passed into init
        self.pca9685_address = pca9685_address
        self.i2c = None

        # Servo Variable Definitions
        # Using nested Dicts because Dataclasses are not in MicroPython
        # Note: relying on GIL to handle synchronization/resource sharing of fingers
        self.fingers = { # other state vars - fully closed/open, P I D, previous curernt pos - current pos = rise (D)  running sum - (I)
            'thumb': {'servo_channel': 9, 'set_point': 0, 'curr_point': 0, 'OTHER_STATE_VARS': []}, ## replicate for fingers
            'index':  {'servo_channel': 10, 'set_point': 0, 'curr_point': 0},
            'middle': {'servo_channel': 7,  'set_point': 0, 'curr_point': 0},
            'ring':   {'servo_channel': 11, 'set_point': 0, 'curr_point': 0},
            'pinky':  {'servo_channel': 8,  'set_point': 0, 'curr_point': 0},
        }

    #c + v from old servo controller script
    def init_i2c(self):
        log.info("attempting to connect to PCA9685")
        try:
            self.i2c = I2C(0, scl=Pin(1), sda=Pin(0), freq=100000)
            self.i2c.writeto_mem(self.pca9685_address, self.MODE1, b'\x10') #
            time.sleep(0.01)
            prescale = int(25000000.0 / (4096 * 50) - 1)
            self.i2c.writeto_mem(self.pca9685_address, self.PRESCALE, bytes([prescale])) #
            time.sleep(0.01)
            self.i2c.writeto_mem(self.pca9685_address, self.MODE1, b'\x00') #
            time.sleep(0.01)
            self.i2c.writeto_mem(self.pca9685_address, self.MODE1, b'\xa0') #
            time.sleep(0.01)
            log.info("PCA9685 connection successful")
            return True
        except Exception as e:
            log.error(f"Init Failed: {e}")
            self.i2c = None
            return False

    def set_servo(self, channel, pulse):
        log.debug(f"set_servo channel {channel} pulse {pulse}")
        off = pulse
        try:
            self.i2c.writeto_mem(self.pca9685_address, self.LED0_ON_L + 4 * channel, b'\x00\x00')
            self.i2c.writeto_mem(self.pca9685_address, self.LED0_ON_L + 4 * channel + 2, bytes([off & 0xFF, off >> 8]))
        except Exception as e:
            log.error(f"set_servo channel {channel} pulse {pulse} failed with exception {e}")
    ##if statement to not call set_servo if not connected to pca9685

    def percent_to_pulse(self, percent):
        # Maps 0-100% from browser to 150(min) - 600(max) servo pulse
        return int(self.min_servo_pulse + (percent / 100.0) * (self.diff_servo_pulse))

    # def servo_control(): ## code for servo control, global for last function call time (ts)
    def servo_control(self):
        for name, data in self.fingers.items():
            target = data['set_point']
            current = data['curr_point']

            log.debug(f"finger {name} target {target} current {current}")

            # Linear Interpolation (Lerp)
            if abs(target - current) > 1:
                current += (target - current) * self.SMOOTHING_FACTOR # Move a fraction of the distance towards the target point
                data['curr_point'] = current

                if self.i2c is not None:
                    self.set_servo(data['servo_channel'], int(current)) # Send updated pulse to the PCA9685

    async def servo_control_loop(self):
        log.info(f"servo_control_loop() started")
        while True:
            self.servo_control()
            self.fingers_tui()
            await uasyncio.sleep_ms(20) # ~50Hz update rate for the lerp smoothing

    def fingers_tui(self):
        print(f"\rFingers: Th {self.fingers['thumb']['set_point']}/{round(self.fingers['thumb']['curr_point'], 2)} Pt {self.fingers['index']['set_point']}/{round(self.fingers['index']['curr_point'], 2)} Md {self.fingers['middle']['set_point']}/{round(self.fingers['middle']['curr_point'], 2)} In {self.fingers['ring']['set_point']}/{round(self.fingers['ring']['curr_point'], 2)} Pk {self.fingers['pinky']['set_point']}/{round(self.fingers['pinky']['curr_point'], 2)}", end="")


class WiFiManager:
    def __init__(self, ssid, password, static_ip, subnet_mask, gateway, dns):
        self.ssid = ssid
        self.password = password
        self.static_ip = static_ip
        self.subnet_mask = subnet_mask
        self.gateway = gateway
        self.dns = dns

    #same wifi script
    def connect_wifi(self):
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.ifconfig((self.static_ip, self.subnet_mask, self.gateway, self.dns))
        wlan.connect(self.ssid, self.password)

        while not wlan.isconnected():
            time.sleep(0.5)

        log.info(f"Connected! http://{wlan.ifconfig()[0]}")


class HandServer:
    def __init__(self, hand, html):
        self.hand = hand
        self.HTML = html
        self.app = tinyweb.webserver()
        self.app.route('/')(self.index)
        self.app.route('/d')(self.set_fingers)

    # Index page  same as the old "GET / " branch
    async def index(self, request, response):
        log.debug(f"index.html requested")
        await response.start_html()
        await response.send(self.HTML)

    # Finger same URL/query-string shape as the old "GET /d?..."
    async def set_fingers(self, request, response):
        try:
            qs = request.query_string
            if qs:
                if isinstance(qs, bytes):
                    qs = qs.decode()
                log.debug(f"set_fingers request string {qs}")
                for p in qs.split('&'):
                    if '=' in p and not p.startswith('ts='): #doesnt get thumb cofused w timestanp
                        name, val = p.split('=') #finds the values
                        try:
                            self.hand.fingers[name]['set_point'] = self.hand.percent_to_pulse(int(val))
                        except (KeyError, ValueError) as e:
                            log.warning(f"Bad finger update '{p}': {e}")
        except Exception as e:
            log.error(f"Error parsing query string: {e}")

        # Report back the current servo position (curr_point, after
        # the lerp smoothing).
        status = {}
        for name, data in self.hand.fingers.items():
            pct = (data['curr_point'] - self.hand.min_servo_pulse) / self.hand.diff_servo_pulse * 100
            status[name] = round(max(0, min(100, pct)))

        log.debug(f"resonse request json {status}")

        response.add_header('Content-Type', 'text/html')
        await response._send_headers()
        await response.send(ujson.dumps(status))


def run():
    #bring website into memory
    with open('index.html', 'r', encoding='utf-8') as f:
        HTML = f.read()

    hand = HandController()
    if not hand.init_i2c():
        log.warning("PCA9685 init failed, continuing anyway")

    wifi = WiFiManager(
        secret.SSID,
        secret.PASSWORD,
        secret.STATIC_IP,
        secret.SUBNET_MASK,
        secret.GATEWAY,
        secret.DNS,
    )
    wifi.connect_wifi()

    server = HandServer(hand, HTML)

    uasyncio.create_task(hand.servo_control_loop())

    log.info("Server live. Visit the IP above in Chrome.")
    server.app.run(host='0.0.0.0', port=80)


if __name__ == '__main__':
    run()
