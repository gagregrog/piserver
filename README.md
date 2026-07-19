## MPD Pi Bridge

### Setup

Clone the repo onto the Pi, then run:

```bash
make setup
```

This installs system packages, creates the virtualenv, installs dependencies, registers and starts the systemd service.

### Service Commands

```bash
make update   # git pull + install deps + restart
make restart  # restart the service
make start    # start the service
make stop     # stop the service
make status   # show service status
make logs     # tail service logs
make ldr      # start the ldr script for tuning photoresistor
```

## Usage

Access the API via the pi's hostname, for example raspberrypi.local.

View the available routes at http://{hostname}.local:8000/docs

Send a post to the available endpoints. For example, to play the queue:

```bash
curl -X POST http://{hostname}.local:8000/play
```

### Privileged actions (passwordless sudo)

A few endpoints shell out to `systemctl` and therefore need root:

- `POST /service/mopidy/restart` — restart the mopidy service
- `POST /system/reboot` — reboot the Pi
- `POST /system/shutdown` — power the Pi off

For each, the `pi` user must be granted passwordless sudo for that specific command. Run `sudo visudo` on the Pi and add these lines at the end of the file:

```
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart mopidy
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl reboot
pi ALL=(ALL) NOPASSWD: /usr/bin/systemctl poweroff
```

> **⚠️ The path must match exactly.** sudo matches on the full binary path, so `systemctl` must be written with its real location. On current Raspberry Pi OS that's `/usr/bin/systemctl` (as used above). **Verify it on your Pi first:**
>
> ```
> which systemctl
> ```
>
> If it prints a different path (older images used `/bin/systemctl`), use that instead. A mismatch means sudo still prompts for a password and the endpoint returns `401`. Confirm a rule works without rebooting: `sudo -n systemctl restart mopidy && echo OK` — `-n` fails instead of prompting if the rule is wrong.

`visudo` changes take effect immediately (no restart needed). Without the matching line, the corresponding endpoint returns a `401` error. (Reboot, shutdown, and mopidy restart are exposed in the ESP32 web UI's Settings modal, each behind a confirmation dialog.)

## Configuration

All device-local configuration lives in `piserver.json` in the repo root. This file is gitignored and never committed — each device has its own copy. Use `piserver.example.json` as a starting point:

```bash
cp piserver.example.json piserver.json
```

The full schema:

```json
{
  "stereo_sensor": { "enabled": false },
  "quickplay": [
    { "items": [{ "artist": "Artist Name", "album": "Album Name" }] },
    { "items": [{ "artist": "One Artist" }, { "artist": "Another Artist" }] },
    { "shuffle": true }
  ],
  "ir": [
    {
      "name": "power",
      "class": "system",
      "sirc": { "address": "0x10", "command": "0x2E" },
      "repeat": 3,
      "delay": 3.0
    },
    {
      "name": "input",
      "class": "stereo",
      "default": true,
      "sirc": { "address": "0x10", "command": "0x12" },
      "repeat": 3,
      "delay": 0.5
    }
  ]
}
```

All sections are optional. If `piserver.json` is absent or a section is missing, that feature is silently disabled and playback continues normally.

- **`stereo_sensor`** — photoresistor power-sensor config (see below). Set `enabled: true` to activate it; the server then checks whether the stereo is on before sending the `input` command, and powers it on first if needed. Defaults to disabled. Other keys (`address`, `channel`, `gain`, `on_threshold`, `off_threshold`) configure the ADS1115 and detection thresholds.
- **`quickplay`** — list of entries for the `/quickplay/{index}` endpoints. An entry is either `{ "shuffle": true }` (shuffle the whole library) or `{ "items": [...] }` whose items play sequentially (one queue, played from the top). Each item has `artist` and optionally `album`.
- **`ir`** — IR command codes for the stereo. Keys map to Sony SIRC commands. Each entry supports optional metadata fields in addition to the hardware fields: `class` (a display group name shown in the web UI), `label` (human-friendly button text, falling back to `name`), and `default: true` (marks the input-select command sent before playback begins). See the IR Blaster section below for field details.

## IR Blaster (Sony Stereo Input Control)

When a play command is received the server sends an IR signal to switch the Sony stereo to the correct input before starting playback.

### IR LED Transmitter

#### Parts

- Adafruit Super-bright 5mm IR LED (ADA388, 940 nm) [chain two together for better signal]
- 2N2222A NPN transistor
- 33 Ω resistor (LED current limiter)
- 1 kΩ resistor (transistor base)
- 100 nF ceramic capacitor (decoupling, optional but recommended)

**Why GPIO 12?** The Waveshare audio HAT uses I2S, which occupies GPIO 18 (BCLK) — the usual hardware PWM0 pin. GPIO 12 is the alternate hardware PWM0 mapping and is free.

#### Wiring

```
5V  (Pin  2) ──[33Ω]──[ADA388 anode→cathode]──┐
                                               Collector
                                            [2N2222A NPN]
                                               Base ──[1kΩ]── GPIO 12 (Pin 32)
                                               Emitter
GND (Pin 34) ──────────────────────────────────┘
```

Anode is the longer lead of the LED. Point the LED directly at the stereo's IR receiver window — the ADA388 has a narrow 20° beam, so aim matters.

With the flat part of the transistor facing you, the pinout is EBC (eat big cookie).

#### Pi Pinout

![pi pinout](./images/pi-pinout.png)

#### System Configuration

**1. Enable the kernel IR transmitter overlay.**

On Pi OS Bookworm:

```bash
sudo nano /boot/firmware/config.txt
```

On Bullseye or earlier:

```bash
sudo nano /boot/config.txt
```

Add at the end of the file:

```ini
dtoverlay=gpio-ir-tx,gpio_pin=12
```

Reboot:

```bash
sudo reboot
```

After rebooting, `/dev/lirc0` should appear.

**2. Grant the `pi` user access to the LIRC device.**

```bash
echo 'SUBSYSTEM=="lirc", MODE="0660", GROUP="pi"' | sudo tee /etc/udev/rules.d/99-lirc.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

**3. Install `ir-keytable`** (included in `make setup`, or install manually):

```bash
sudo apt install -y ir-keytable
```

### Discovering Your Sony SIRC Command

You need the **address** and **command** values for each button on your Sony stereo.

- **A / address** — identifies the device type (e.g. amplifier, TV). Only the device with a matching address responds.
- **C / command** — the action to perform (input select, volume up, etc.).

Use a Flipper Zero: point your Sony remote at it and capture the button press. It will report something like `SIRC A: 0x10 C: 0x12`.

### IR Command Configuration

`"ir"` in `piserver.json` is an array of command objects. Address and command values can be hex strings (`"0x10"`) or decimal integers (`16`).

Per-command fields:

- **`name`** — unique identifier for this command, used in the `POST /ir/{name}` API. The endpoint accepts an optional `count` query param (e.g. `POST /ir/volumeUp?count=3`) to send the command as that many discrete presses in a single request — each press is a full `repeat`-frame burst separated by `delay`. Defaults to `1`.
- **`class`** — display group shown in the web UI (e.g. `"system"`, `"input"`).
- **`label`** — human-friendly button text shown in the web UI (e.g. `"Apple TV"`). Optional; falls back to `name` when omitted. Returned by `GET /ir` alongside `name` and `class`.
- **`default`** — set to `true` on the command the server sends before starting playback (input-select). Only one entry should have this.
- **`sirc`** — object with `address` and `command`. The SIRC variant is selected automatically based on address width: addresses up to `0x1F` use SIRC-12 (5-bit address); addresses up to `0xFF` use SIRC-15 (8-bit address).
- **`repeat`** — number of times to send the frame. Sony SIRC requires `3`. Defaults to `1`.
- **`delay`** — seconds to wait after sending. Useful for the input command (stereo input switch time) or power command (stereo boot time). Omit or set to `0` for no delay.

The entry with `"name": "power"` is sent first when the sensor detects the stereo is off (see below).

### Testing

With `piserver.json` configured, trigger the command through the API:

```bash
curl -X POST http://{hostname}.local:8000/play
```

The server logs will show `ir_blaster: sent sony12 A:0x10 C:0x12 x3`. If you have a Flipper Zero, point it at the LED while triggering to verify the transmitted address and command match what your remote sends.

### Photoresistor Power Sensor (optional — auto power-on)

When `stereo_sensor.enabled: true` is set in `piserver.json`, the server reads a photoresistor aimed at the stereo's power LED before sending the input-select command. When the stereo is off (no LED light detected), it first sends the `"power"` IR command and waits for the stereo to boot, then sends `"input"`.

The sensor is also exposed over HTTP so other devices (e.g. the ESP32 controller) can query power state and manage the sensor entirely from the web UI:

- `GET /stereo` → `{"on": true|false|null, "voltage": float|null, "sensor_enabled": bool}`
- `GET /stereo/config` → the current `stereo_sensor` block with defaults applied (`address` normalized to a hex string) — populates the settings form
- `PUT /stereo/config` → merge the posted fields (`enabled`, `address`, `channel`, `gain`, `on_threshold`, `off_threshold`) into `stereo_sensor`, persist, and re-initialize the ADC so hardware changes take effect without a restart
- `POST /stereo/sample?count=100` → take a burst of readings and return `{count, mean, min, max, stdev, as_on_threshold, as_off_threshold}` **without** writing anything; the UI uses this to tune one threshold at a time

`on` is the sensor reading — `true` (LED lit), `false` (dark), or `null` when the sensor is unavailable. `voltage` is the raw ADS1115 reading in volts (`null` if the ADC is unavailable). The reading is taken regardless of `stereo_sensor.enabled`; `sensor_enabled` reports whether the auto power-on logic actually acts on it.

You can configure and tune the sensor without editing `piserver.json` by hand: open the ESP32 web UI's **Settings** modal → **Configure Sensor**. It shows every value as an editable field, with a **Tune** button beside each threshold that runs a sample burst (`/stereo/sample`) and fills in a suggested value. **Save** writes the whole block via `PUT /stereo/config`.

The Pi has no analog input, so an **ADS1115 ADC** (over I2C) reads the LDR divider voltage and the on/off threshold is applied in software with hysteresis. Configure it under `stereo_sensor` in `piserver.json`:

```json
"stereo_sensor": {
  "enabled": false,         // true => sensor drives auto power-on
  "address": "0x48",       // I2C address (int or hex string)
  "channel": 0,             // input channel A0..A3
  "gain": 1,                // PGA gain (2/3, 1, 2, 4, 8, 16)
  "on_threshold": 2.0,      // volts, reading >= this => ON
  "off_threshold": 1.5      // volts, reading <= this => OFF
}
```

All keys are optional. `enabled` defaults to `false` (sensor readable via `/stereo` but not driving auto power-on); the rest fall back to the defaults shown above.

#### Parts

- ADS1115 16-bit ADC breakout
- LDR (photoresistor, any common 5 mm type)
- One fixed resistor for the LDR divider (see tuning below)

Aim the LDR at the power LED and shroud it (heatshrink / short tube) to block ambient light — reliability depends far more on a clean on/off light gap than on the electronics.

#### Wiring

ADS1115 on the I2C bus, LDR divider into A0:

```
ADS1115         Pi
  VDD  ───────  3.3V (Pin  1)
  GND  ───────  GND  (Pin  9)
  SCL  ───────  GPIO 3 / SCL (Pin  5)
  SDA  ───────  GPIO 2 / SDA (Pin  3)
  ADDR ───────  GND          (I2C address 0x48)

3.3V ──[LDR]──┬── A0 (ADS1115)
             [R]
              │
             GND
```

- **Stereo on (LED lit):** LDR resistance drops → A0 voltage rises → above `on_threshold`
- **Stereo off (dark):** LDR resistance rises → A0 voltage falls → below `off_threshold`

Pick the divider resistor `R` near the **geometric mean** of the LDR's lit and dark resistances (`R ≈ √(R_on × R_off)`, measured with a multimeter) to maximize the on/off voltage swing.

**Measured on this stereo** (for reference — yours may differ with LED brightness and how the LDR is aimed/shrouded):

| State          | LDR resistance | A0 voltage (R = 62 kΩ) |
| -------------- | -------------- | ---------------------- |
| LED on (lit)   | 40.1 kΩ        | 2.00 V                 |
| LED off (dark) | 96.7 kΩ        | 1.29 V                 |

That's only a 2.4× resistance ratio, so `R ≈ 62 kΩ` (nearest standard: 62 kΩ or 68 kΩ) gives the widest swing — a ~0.71 V gap between on and off. The Pi's GPIO couldn't resolve that (both voltages sit in the digital gray zone, which is why a comparator was originally needed), but the ADS1115 reads the raw voltage, so 0.71 V is plenty. Suitable thresholds for these readings: `on_threshold` ≈ 1.8, `off_threshold` ≈ 1.5. A trimmer pot in place of `R` (≈100 kΩ, wired as a rheostat) lets you tune the window at install time; the gap stays ~0.7 V anywhere from ~50–100 kΩ, so the exact setting isn't critical.

**Why I2C?** GPIO 18–21 are claimed by the Waveshare WM8960 HAT (I2S audio), GPIO 12 is IR TX, GPIO 24 is IR RX. The ADS1115 rides the existing I2C bus on GPIO 2/3, so it needs no dedicated GPIO.

**I2C is already enabled.** The WM8960 is an I2C-controlled codec — the `wm8960-soundcard` service waits for it to appear on I2C, so `dtparam=i2c_arm=on` is already in effect on any Pi where audio works. No conflict either: the WM8960 lives at address `0x1a`, the ADS1115 at `0x48`, so they share the bus fine.

#### Setup

1. Confirm the bus and devices: `i2cdetect -y 1`. You should already see `1a` (the WM8960 — proof I2C is up). If for some reason it's off, enable it with `sudo raspi-config` → Interface Options → I2C and reboot.
2. Install deps (included in `requirements.txt`): `pip install -r requirements.txt`
3. Wire the ADS1115 and re-run `i2cdetect -y 1` — `48` should now appear alongside `1a`. (If you ever run two ADS1115s, strap the second one's `ADDR` pin to `0x49`/`0x4A`/`0x4B` and set `address` accordingly.)

#### Tuning thresholds

**From the web UI (easiest):** Settings → Configure Sensor → **Tune** beside each threshold (see above). No SSH needed.

The command-line tools below do the same thing over SSH.

Automatic calibration (recommended once installed):

```bash
make calibrate    # or: python3 scripts/sense_stereo_ads.py --calibrate
```

This prompts you to turn the stereo **off** (samples 100 readings), then **on** (another 100), then computes `on_threshold` / `off_threshold` that sit in the gap between the two clusters and writes them to `stereo_sensor` in `piserver.json`. It refuses to write if the on/off ranges overlap or if the on reading isn't the higher voltage. Restart with `make restart` afterward. Use `--samples N` to change the sample count.

Manual monitoring:

```bash
make ldr          # or: python3 scripts/sense_stereo_ads.py
```

This prints the live A0 voltage and the current on/off decision. Turn the stereo on and off, note the two voltages, then set `on_threshold` just below the lit voltage and `off_threshold` just above the dark voltage. The gap between them is the **hysteresis band**: readings inside it hold the previous state, so a value hovering near the edge can't chatter. If the two voltages are very close, increase `gain` (e.g. `2` or `4`) to zoom the ADC into that window for finer resolution — as long as your peak voltage stays within the gain's full-scale range (gain `1` = ±4.096 V, `2` = ±2.048 V).

### IR Receiver (optional — for discovering command codes)

A TSOP38238 wired to the Pi lets you decode your existing Sony remote. This is only needed if you don't have a Flipper Zero and want to read codes directly on the Pi.

#### Parts

- TSOP38238, VS1838B, or any 38 kHz demodulating IR receiver (3 pins: Out, GND, Vs)

#### Wiring

TSOP38238 pinout: flat side facing you, leads pointing down — Out / GND / Vs left to right.

```
5V   (Pin  2) ─────────────────── Vs  (pin 3)
                               [TSOP38238]
GND  (Pin 34) ─────────────────── GND (pin 2)
GPIO 24 (Pin 16) ──────────────── Out (pin 1)
```

#### System Configuration

Add the receiver overlay alongside the transmitter line in `config.txt`:

```ini
dtoverlay=gpio-ir-tx,gpio_pin=12
dtoverlay=gpio-ir,gpio_pin=24
```

Reboot. After rebooting, `/dev/lirc1` should appear alongside `/dev/lirc0`.

### Quick Play

The `quickplay` section of `piserver.json` defines a numbered list of entries for the `/quickplay/{index}` endpoints. An entry is either a shuffle-all or an `items` array whose items are queued and played sequentially, so one badge can play several artists/albums back to back:

```json
{"shuffle": true}                                              // shuffle the whole library
{"items": [{"artist": "Artist Name", "album": "Album Name"}]}  // one specific album
{"items": [{"artist": "Artist Name"}]}                         // all albums by artist
{"items": [{"artist": "A"}, {"artist": "B", "album": "X"}]}    // A's albums, then B's album X
```

Each item supports `artist` and optionally `album`. Shuffle is an entry-level flag (`{"shuffle": true}`) that plays the whole library randomized — it is not combined with specific items.

The list can also be managed via the API:

- `GET /quickplay` — return the full list
- `PUT /quickplay` — replace the full list
- `PUT /quickplay/{index}` — update or append a single entry
- `POST /quickplay/{index}` — trigger playback for that entry
