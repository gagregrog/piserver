#!/usr/bin/env python3
"""Monitor or calibrate the ADS1115 stereo sensor.

Usage:
    python3 scripts/sense_stereo_ads.py              # live monitor (default)
    python3 scripts/sense_stereo_ads.py --calibrate  # guided threshold setup

Monitor mode prints the live voltage from the configured ADS1115 channel
alongside the on/off decision from the configured thresholds.

Calibrate mode samples the stereo OFF, then ON, computes on/off thresholds that
sit in the gap between the two, and writes them to `stereo_sensor` in
piserver.json.

Reads ADS1115 config (address, channel, gain, thresholds) from piserver.json.
"""

import argparse
import os
import statistics
import sys
import time

# Allow running as `python3 scripts/sense_stereo_ads.py` from the piserver root:
# add that root to the import path so `stereo_sensor` / `config` resolve.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import stereo_sensor

POLL_SECONDS = 0.25
SAMPLE_COUNT = 100
SAMPLE_DELAY = 0.02
# Thresholds are placed this fraction of the gap in from each cluster edge, so
# the hysteresis deadband spans the middle (1 - 2*MARGIN) of the gap.
GAP_MARGIN = 0.25
MIN_GAP_VOLTS = 0.2


def _unavailable_msg():
    print("voltage: unavailable — check wiring, I2C address, and that "
          "adafruit-circuitpython-ads1x15 + adafruit-blinka are installed")


def monitor():
    cfg = stereo_sensor._cfg()
    on_t = cfg.get("on_threshold", stereo_sensor.DEFAULT_ON_THRESHOLD)
    off_t = cfg.get("off_threshold", stereo_sensor.DEFAULT_OFF_THRESHOLD)
    print(f"Thresholds: ON >= {on_t} V, OFF <= {off_t} V (band held by hysteresis).")
    print("Reading ADS1115. Ctrl+C to exit.\n")

    while True:
        v = stereo_sensor.read_voltage()
        if v is None:
            _unavailable_msg()
        else:
            on = stereo_sensor._resolve_state(v)
            label = "ON " if on else ("OFF" if on is False else "???")
            print(f"[{time.strftime('%H:%M:%S')}] {v:6.3f} V  -> {label}")
        time.sleep(POLL_SECONDS)


def _sample(n):
    """Collect n voltage readings, skipping unavailable ones. Returns the list."""
    samples = []
    misses = 0
    while len(samples) < n:
        v = stereo_sensor.read_voltage()
        if v is None:
            misses += 1
            if misses > n:
                break
            continue
        samples.append(v)
        print(f"\r  sampling... {len(samples)}/{n}", end="", flush=True)
        time.sleep(SAMPLE_DELAY)
    print()
    return samples


def _summarize(label, samples):
    lo, hi = min(samples), max(samples)
    mean = statistics.fmean(samples)
    stdev = statistics.pstdev(samples)
    print(f"  {label}: mean {mean:.3f} V, min {lo:.3f} V, max {hi:.3f} V, "
          f"stdev {stdev:.4f} V ({len(samples)} samples)")
    return {"lo": lo, "hi": hi, "mean": mean}


def _prompt(message):
    try:
        input(message)
        return True
    except (EOFError, KeyboardInterrupt):
        print("\nCalibration aborted.")
        return False


def calibrate(n):
    print("ADS1115 stereo sensor calibration.")
    print(f"Will take {n} samples in each state and compute thresholds.\n")

    if stereo_sensor.read_voltage() is None:
        _unavailable_msg()
        return 1

    if not _prompt("Turn the stereo OFF, then press Enter to sample... "):
        return 1
    off = _sample(n)
    if not off:
        _unavailable_msg()
        return 1
    off_stats = _summarize("OFF", off)

    if not _prompt("\nTurn the stereo ON, then press Enter to sample... "):
        return 1
    on = _sample(n)
    if not on:
        _unavailable_msg()
        return 1
    on_stats = _summarize("ON ", on)

    # The sensor logic treats higher voltage as ON. Confirm the clusters are
    # ordered that way and separated before deriving thresholds.
    if on_stats["mean"] <= off_stats["mean"]:
        print("\nERROR: the ON reading is not higher than the OFF reading.")
        print("The sensor logic requires ON to be the higher voltage. Check the")
        print("wiring (LDR on the 3.3V side of the divider) and retry.")
        return 1

    off_hi, on_lo = off_stats["hi"], on_stats["lo"]
    gap = on_lo - off_hi
    if gap <= 0:
        print(f"\nERROR: the OFF and ON ranges overlap (OFF max {off_hi:.3f} V "
              f">= ON min {on_lo:.3f} V).")
        print("Cannot pick reliable thresholds. Improve LDR placement / shielding.")
        return 1
    if gap < MIN_GAP_VOLTS:
        print(f"\nWARNING: small separation ({gap:.3f} V) between OFF and ON. "
              "Detection may be marginal.")

    off_threshold = round(off_hi + gap * GAP_MARGIN, 3)
    on_threshold = round(on_lo - gap * GAP_MARGIN, 3)

    print(f"\nProposed thresholds:")
    print(f"  on_threshold  = {on_threshold} V")
    print(f"  off_threshold = {off_threshold} V")
    print(f"  (hysteresis deadband {off_threshold}–{on_threshold} V)")

    if not _prompt("\nWrite these to piserver.json? Press Enter to write, "
                   "Ctrl+C to cancel... "):
        return 1

    data = config.load()
    sensor = dict(data.get("stereo_sensor") or {})
    sensor["on_threshold"] = on_threshold
    sensor["off_threshold"] = off_threshold
    data["stereo_sensor"] = sensor
    config.save(data)
    print(f"Wrote thresholds to {config.CONFIG_FILE}.")
    if not data.get("use_sensor"):
        print('Note: "use_sensor" is false — set it true to enable the sensor.')
    print("Restart the service to pick up changes: make restart")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--calibrate", action="store_true",
                        help="guided OFF/ON sampling that writes thresholds to piserver.json")
    parser.add_argument("--samples", type=int, default=SAMPLE_COUNT,
                        help=f"samples per state in calibrate mode (default {SAMPLE_COUNT})")
    args = parser.parse_args()

    if args.calibrate:
        return calibrate(args.samples)
    monitor()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
