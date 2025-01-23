#!/usr/bin/env python3
import threading
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

GPIO = 18
FREQ = 38.0


def log_verbose(msg: str) -> str:
    if VERBOSE:
        print(msg)
    return msg


def log_info(msg: str) -> str:
    print(msg)
    return msg


class IRtx(threading.Thread):
    def __init__(self, gpio, freq):
        super().__init__()
        self._gpio = gpio
        self._freq = freq

        self._pi = None
        self._todo = []
        self._continue = True

    def run(self):
        while self._continue:
            if self._todo:
                log_verbose("Connect to pi")
                self._pi = pigpio.pi()  # Connect to Pi.
                self._pi.set_mode(self._gpio, pigpio.OUTPUT)  # IR TX connected to this gpio.

                # play all queued codes
                while self._todo:
                    (key, code) = self._todo.pop()
                    IRtx.send_code(self._pi, key, code, self._gpio, self._freq)

                log_verbose("Disconnect from Pi.")
                self._pi.stop()
                self._pi = None

            time.sleep(0.05)

    def queue_code(self, key, code):
        self._todo.append((key, code))

    def stop(self):
        self._continue = False

    @staticmethod
    def send_code(pi, key, code, gpio, freq):
        log_verbose(f"Playing '{key}'")
        pi.wave_add_new()

        # Check marks
        marks = {}
        for i in range(0, len(code), 2):
            if code[i] not in marks:
                marks[code[i]] = -1

        for i in marks:
            wf = IRtx.carrier(gpio, freq, i)
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

    @staticmethod
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


class MyServer(BaseHTTPRequestHandler):
    def do_GET(self):
        global irtx

        log_verbose(f"Received '{self.path}'")
        param = self.path.split("?")
        if len(param) == 2 and param[0] == '/switch':
            log_verbose(f"Param '{param[1]}'")
            param = param[1].split("=")
            if len(param) == 2 and param[0] == 'id':
                key = param[1]
                log_verbose(f"Switch id 'key'")
                if key in ROBLIN_IR:
                    msg = log_info(f"Switching <b>'{key}'</b>")
                    irtx.queue_code(key, ROBLIN_IR[key])
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


if __name__ == "__main__":
    # Start the IR TX thread
    irtx = IRtx(GPIO, FREQ)
    irtx.start()

    webServer = HTTPServer((HOSTNAME, PORT), MyServer)
    log_info("Server started http://%s:%s" % (HOSTNAME, PORT))

    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass
    webServer.server_close()

    irtx.stop()
    irtx.join()
    log_verbose("Server stopped.")
