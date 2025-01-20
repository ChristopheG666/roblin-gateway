#!/usr/bin/env python3

from http.server import BaseHTTPRequestHandler, HTTPServer
import pigpio
import time

ROBLIN_IR = {"light": [762, 689, 762, 689, 1506, 1378, 762, 689, 762, 689, 1506, 2784, 762, 689, 762, 689, 2238],
             "max": [766, 704, 1494, 1378, 766, 704, 766, 704, 1494, 1378, 766, 2082, 1494, 2082, 1494],
             "moins": [744, 1403, 1492, 707, 744, 707, 744, 1403, 1492, 707, 744, 2790, 1492, 1403, 1492],
             "plus": [734, 718, 2247, 718, 734, 718, 734, 718, 2247, 718, 734, 2095, 2247, 1398, 1462],
             "power": [728, 718, 728, 1420, 1492, 718, 728, 718, 728, 1420, 1492, 2088, 728, 1420, 728, 718, 1492]}

VERBOSE = True

HOSTNAME = "0.0.0.0"
PORT = 8080

GPIO = 17
FREQ = 38

def log_verbose(msg: str) -> str:
    if VERBOSE:
        print(msg)
    return msg


def log_info(msg: str) -> str:
    print(msg)
    return msg


class MyServer(BaseHTTPRequestHandler):
    def do_GET(self):

        log_verbose(f"Received '{self.path}'")
        param = self.path.split("?")
        msg = ''
        if len(param) == 2 and param[0] == '/switch':
            log_verbose(f"Param '{param[1]}'")
            param = param[1].split("=")
            if len(param) == 2 and param[0] == 'id':
                key = param[1]
                log_verbose(f"Switch id 'key'")
                if key in ROBLIN_IR:
                    msg = log_info(f"Switching <b>'{key}'</b>")
                    send_code(ROBLIN_IR[key], 17, 38)
                else:
                    msg = log_info(f"Unknown key <b>'{key}'</b>")
            else:
                msg = log_info(f"Invalid request: <b>'{self.path}'</b>'")
        else:
            msg = log_info(f"Invalid request: <b>'{self.path}'</b>")

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(bytes("<html><head><title>Roblin Wifi gatweway</title></head>", "utf-8"))
        self.wfile.write(bytes("<body>", "utf-8"))
        self.wfile.write(bytes(f"<p>{msg}</p>", "utf-8"))
        self.wfile.write(bytes("</body></html>", "utf-8"))

def carrier(gpio, frequency, micros, dutycycle=0.5):
    """
    Generate cycles of carrier on gpio with frequency and dutycycle.
    """
    wf = []
    cycle = 1000.0 / frequency
    cycles = int(round(micros / cycle))
    on = int(round(cycle * dutycycle))
    sofar = 0
    for c in range(cycles):
        target = int(round((c + 1) * cycle))
        sofar += on
        off = target - sofar
        sofar += off
        wf.append(pigpio.pulse(1 << gpio, 0, on))
        wf.append(pigpio.pulse(0, 1 << gpio, off))
    return wf

def send_code(code, GPIO, FREQ):
    pi = pigpio.pi()  # Connect to Pi.
    pi.set_mode(GPIO, pigpio.OUTPUT)  # IR TX connected to this GPIO.

    pi.wave_add_new()

    print("Playing")

    # Check marks
    marks = {}
    for i in range(0, len(code), 2):
        if code[i] not in marks:
            marks[code[i]] = -1

    for i in marks:
        wf = carrier(GPIO, FREQ, i)
        pi.wave_add_generic(wf)
        wid = pi.wave_create()
        marks[i] = wid

    # Check spaces
    spaces = {}
    for i in range(1, len(code), 2):
        if code[i] not in spaces:
            spaces[code[i]] = -1

    for i in spaces:
        pi.wave_add_generic([pigpio.pulse(0, 0, i)])
        wid = pi.wave_create()
        spaces[i] = wid

    # Create wave
    wave = [0] * len(code)
    for i in range(0, len(code)):
        if i & 1:  # Space
            wave[i] = spaces[code[i]]
        else:  # Mark
            wave[i] = marks[code[i]]

    pi.wave_chain(wave)

    while pi.wave_tx_busy():
        time.sleep(0.05)

    for i in marks:
        pi.wave_delete(marks[i])
    for i in spaces:
        pi.wave_delete(spaces[i])

if __name__ == "__main__":
    webServer = HTTPServer((HOSTNAME, PORT), MyServer)
    print("Server started http://%s:%s" % (HOSTNAME, PORT))

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass

    webServer.server_close()
    print("Server stopped.")
