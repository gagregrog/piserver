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
```

## Usage

Access the API via the pi's hostname, for example raspberrypi.local.

View the available routes at http://{hostname}.local:8000/docs

Send a post to the available endpoints. For example, to play the queue:

```bash
curl -X POST http://{hostname}.local:8000/play
```

### Restarting Mopidy

The `POST /service/mopidy/restart` endpoint restarts the mopidy service. Because this requires sudo, the `pi` user must be granted passwordless sudo for that specific command.

Run `sudo visudo` on the Pi and add this line at the end of the file:

```
pi ALL=(ALL) NOPASSWD: /bin/systemctl restart mopidy
```

Without this, the endpoint returns a `401` error.

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

### IR Receiver (optional — for discovering command codes)

A TSOP38238 wired to the Pi lets you decode your existing Sony remote using `ir-keytable`. This is only needed if you don't have a Flipper Zero and want to read codes directly on the Pi.

#### Parts

- TSOP38238, VS1838B, or any 38 kHz demodulating IR receiver (3 pins: Out, GND, Vs)

#### Wiring

TSOP38238 pinout: flat side facing you, leads pointing down — Out / GND / Vs left to right.

```
5V   (Pin  2) ─────────────────── Vs  (pin 3)
                               [TSOP38238]
GND  (Pin 34) ─────────────────── GND (pin 2)
GPIO 23 (Pin 16) ──────────────── Out (pin 1)
```

#### System Configuration

Add the receiver overlay alongside the transmitter line in `config.txt`:

```ini
dtoverlay=gpio-ir-tx,gpio_pin=12
dtoverlay=gpio-ir,gpio_pin=23
```

Reboot. After rebooting, `/dev/lirc1` should appear alongside `/dev/lirc0`.

#### Capturing a Command

```bash
sudo ir-keytable -p sony -t
```

Point your Sony remote at the receiver and press the button you want to capture. You will see output like:

```
173.728070: lirc protocol(sony12): scancode = 0x100025
```

The kernel encodes Sony scancodes as `(address << 16) | command`:
- `address = 0x100025 >> 16 = 0x10`
- `command = 0x100025 & 0xFF = 0x25`

### Discovering Your Sony SIRC Command

You need the **address** and **command** values for the button on your Sony stereo.

- **A / address** — identifies the device type (e.g. amplifier, TV). Only the device with a matching address responds.
- **C / command** — the action to perform (input select, volume up, etc.).

**Option A — Flipper Zero:** point your Sony remote at the Flipper and capture the button press. It will report something like `SIRC A: 0x10 C: 0x12`.

**Option B — IR receiver on the Pi:** follow the IR Receiver setup above and use `ir-keytable` to capture the scancode, then decode it as shown.

### Configuring the IR Command

Create `ir_config.json` in the repo root (it is gitignored and stays local to each device):

```json
{
  "input": {
    "sirc": { "address": "0x10", "command": "0x12" },
    "repeat": 3,
    "switch_delay_s": 0.5
  }
}
```

Address and command values can be hex strings (`"0x10"`) or decimal integers (`16`).

Per-command fields:

- **`sirc`** — object with `address` and `command` for the SIRC-12 frame.
- **`repeat`** — number of times to send the frame. Sony SIRC requires `3`. Defaults to `1`.
- **`switch_delay_s`** — seconds to wait after sending. Useful for `input` to give the stereo time to switch. Omit or set to `0` for no delay.

The `input` key is what the server sends before starting playback. All other keys are available for future use via `ir_blaster.send_command("key")`.

If `ir_config.json` does not exist, or a requested key is absent, IR blasting is silently skipped and playback continues normally.

### Testing

With `ir_config.json` in place, trigger the command through the API:

```bash
curl -X POST http://{hostname}.local:8000/play
```

The server logs will show `ir_blaster: sent sony12 A:0x10 C:0x12 x3`. If you have a Flipper Zero, point it at the LED while triggering to verify the transmitted address and command match what your remote sends.

### Quick Play

`quickplay.json` contains a list of artist/album targets for the `/quickplay/{number}` endpoint. An example is committed to the repo. To customize it locally without your changes being picked up by git, run:

```bash
git update-index --skip-worktree quickplay.json
```

To commit a deliberate update to the example, reverse that first:

```bash
git update-index --no-skip-worktree quickplay.json
```
