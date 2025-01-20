#!/usr/bin/env python

# irrp.py
# 2015-12-13
# Public Domain

import time
import json
import os
import argparse

import pigpio

parser = argparse.ArgumentParser()

group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("-r", "--record", help="record IR codes", action="store_true")
group.add_argument("-p", "--play", help="play IR codes", action="store_true")
group.add_argument("-t", "--tidy", help="tidy data", action="store_true")

parser.add_argument("-g", "--gpio", help="GPIO", type=int, required=True)

parser.add_argument("-f", "--file", help="Filename", required=True)

parser.add_argument('id', nargs='+', type=str, help='IR codes')

parser.add_argument("--pre",    help="preamble millis",  type=int, default=20)
parser.add_argument("--post",   help="postamble millis", type=int, default=20)
parser.add_argument("--glitch", help="glitch micros", type=int,   default=100)
parser.add_argument("--freq",   help="frequency kHz", type=float, default=38.0)

parser.add_argument("-v", "--verbose", help="Be verbose", action="store_true")

args = parser.parse_args()

GPIO = args.gpio
FILE = args.file
GLIT = args.glitch
PRE  = args.pre
POST = args.post
FREQ = args.freq
VERB = args.verbose

PRE_US = PRE * 1000

last_tick = None
in_code = False
code = []
code_done = False

def backup(f):
   try:
      os.rename(os.path.realpath(f)+".bak1", os.path.realpath(f)+".bak2")
   except:
      pass

   try:
      os.rename(os.path.realpath(f)+".bak", os.path.realpath(f)+".bak1")
   except:
      pass

   try:
      os.rename(os.path.realpath(f), os.path.realpath(f)+".bak")
   except:
      pass

def carrier(gpio, frequency, micros, dutycycle=0.5):
   """
   Generate cycles of carrier on gpio with frequency and dutycycle.
   """
   wf = []
   cycle = 1000.0 / frequency
   cycles = int(round(micros/cycle))
   on = int(round(cycle * dutycycle))
   sofar = 0
   for c in range(cycles):
      target = int(round((c+1)*cycle))
      sofar += on
      off = target - sofar
      sofar += off
      wf.append(pigpio.pulse(1<<gpio, 0, on))
      wf.append(pigpio.pulse(0, 1<<gpio, off))
   return wf

def compare(p1, p2):
   if len(p1) != len(p2):
      return False
   for i in range(len(p1)):
      v = p1[i] / p2[i]
      if (v < 0.8) or (v > 1.2):
         return False
   for i in range(len(p1)):
       p1[i] = int(round((p1[i]+p2[i])/2.0))
   return True

def normalise(c):
   entries = len(c)
   p = [0]*entries # Set all entries not processed.
   for i in range(entries):
      if not p[i]: # Not processed?
         v = c[i]
         tot = v
         similar = 1.0
         for j in range(i+2, entries, 2): # Find unprocessed similar.
            if not p[j]: # Unprocessed.
               if c[j]*0.8 < v < c[j]*1.2: # Similar.
                  tot = tot + c[j]
                  similar += 1.0
         newv = tot / similar
         c[i] = newv
         for j in range(i+2, entries, 2): # Normalise similar.
            if not p[j]: # Unprocessed.
               if c[j]*0.8 < v < c[j]*1.2: # Similar.
                  c[j] = newv
                  p[j] = 1

def end_of_code():
   global code, code_done
   if len(code) > 10:
      normalise(code)
      code_done = True
   else:
      code = []
      print("Short code, probably a repeat, try again")


def cbf(gpio, level, tick):
   global last_tick, in_code, code, code_done
   if last_tick is not None:
      if level != pigpio.TIMEOUT:
         edge = pigpio.tickDiff(last_tick, tick)
         if edge > PRE_US: # Start or stop of a code.
            if in_code:
               in_code = False
               pi.set_watchdog(GPIO, 0) # Cancel watchdog.
               end_of_code()
            else:
               if not code_done:
                  in_code = True
                  pi.set_watchdog(GPIO, POST) # Start watchdog.
         else:
            if in_code:
               code.append(edge)
      else: # Timeout.
         pi.set_watchdog(GPIO, 0) # Cancel watchdog.
         if in_code:
            in_code = False
            end_of_code()
   if level != pigpio.TIMEOUT:
      last_tick = tick

pi = pigpio.pi() # Connect to Pi.

if args.record: # Record.

   try:
      f = open(FILE, "r")
      records = json.load(f)
      f.close()
   except:
      records = {}

   pi.set_mode(GPIO, pigpio.INPUT) # IR RX connected to this GPIO.
   pi.set_glitch_filter(GPIO, GLIT) # Ignore glitches.

   cb = pi.callback(GPIO, pigpio.EITHER_EDGE, cbf)

   # Process each id

   print("Recording")
   for arg in args.id:
      code = []
      code_done = False
      print("Press key for '{}'".format(arg))
      while not code_done:
         time.sleep(0.1)
      press_1 = code[:]
      match = False
      while not match:
         code = []
         code_done = False
         print("Press key for '{}' to confirm".format(arg))
         while not code_done:
            time.sleep(0.1)
         press_2 = code[:]
         the_same = compare(press_1, press_2)
         if the_same:
            match = True
            records[arg] = press_1

   backup(FILE)

   f = open(FILE, "w")
   f.write(json.dumps(records, sort_keys=True))
   f.close()

elif args.play: # Playback.

   try:
      f = open(FILE, "r")
   except:
      print("Can't open: {}".format(FILE))
      exit(0)

   records = json.load(f)

   f.close()

   pi.set_mode(GPIO, pigpio.OUTPUT) # IR TX connected to this GPIO.

   pi.wave_add_new()

   print("Playing")
   for arg in args.id:
      if arg in records:
         code = records[arg]

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
         wave = [0]*len(code)
         for i in range(0, len(code)):
            if i & 1: # Space
               wave[i] = spaces[code[i]]
            else: # Mark
               wave[i] = marks[code[i]]

         pi.wave_chain(wave)

         print("key "+arg)

         while pi.wave_tx_busy():
            time.sleep(0.05)

         for i in marks:
            pi.wave_delete(marks[i])
         for i in spaces:
            pi.wave_delete(spaces[i])
      else:
         print("Id {} not found".format(arg))

elif args.tidy: # Tidy data

   try:
      f = open(FILE, "r")
   except:
      print("Can't open: {}".format(FILE))
      exit(0)

   records = json.load(f)

   f.close()

   backup(FILE)

   f = open(FILE, "w")
   f.write(json.dumps(records, sort_keys=True))
   f.close()

pi.stop() # Disconnect from Pi.
