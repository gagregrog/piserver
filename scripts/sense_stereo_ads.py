#!/usr/bin/env python3
"""Monitor the ADS1115 stereo sensor voltage and on/off decision.

Usage:
    python3 scripts/sense_stereo_ads.py

Prints the live voltage from the configured ADS1115 channel alongside the
on/off decision from the configured thresholds. Turn the stereo on and off to
find good `on_threshold` / `off_threshold` values, then set them under
`stereo_sensor` in piserver.json.

Reads ADS1115 config (address, channel, gain, thresholds) from piserver.json.
"""

import os
import sys
import time

# Allow running as `python3 scripts/sense_stereo_ads.py` from the piserver root:
# add that root to the import path so `stereo_sensor` / `config` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import stereo_sensor

POLL_SECONDS = 0.25


def main():
    cfg = stereo_sensor._cfg()
    on_t = cfg.get("on_threshold", stereo_sensor.DEFAULT_ON_THRESHOLD)
    off_t = cfg.get("off_threshold", stereo_sensor.DEFAULT_OFF_THRESHOLD)
    print(f"Thresholds: ON >= {on_t} V, OFF <= {off_t} V (band held by hysteresis).")
    print("Reading ADS1115. Ctrl+C to exit.\n")

    while True:
        v = stereo_sensor.read_voltage()
        if v is None:
            print("voltage: unavailable — check wiring, I2C address, and that "
                  "adafruit-circuitpython-ads1x15 + adafruit-blinka are installed")
        else:
            on = stereo_sensor._resolve_state(v)
            label = "ON " if on else ("OFF" if on is False else "???")
            print(f"[{time.strftime('%H:%M:%S')}] {v:6.3f} V  -> {label}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
