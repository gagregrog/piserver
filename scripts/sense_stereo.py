#!/usr/bin/env python3
"""Monitor the stereo power LED sensor and print state changes.

Usage:
    python3 scripts/sense_stereo.py

Run this while adjusting the potentiometer to find the threshold where the
reading reliably flips between on and off.
"""

import time

try:
    from gpiozero import DigitalInputDevice
except ImportError:
    print("gpiozero not installed — run: pip install gpiozero")
    raise SystemExit(1)

GPIO_PIN = 17

sensor = DigitalInputDevice(GPIO_PIN, pull_up=False)
print(f"Monitoring GPIO {GPIO_PIN}. Turn the stereo on/off and adjust the pot.")
print("Ctrl+C to exit.\n")

last = None
while True:
    current = bool(sensor.value)
    if current != last:
        label = "ON " if current else "OFF"
        print(f"[{time.strftime('%H:%M:%S')}] {label}")
        last = current
    time.sleep(0.05)
