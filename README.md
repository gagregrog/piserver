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

### Hardware

**Parts:**

- Adafruit Super-bright 5mm IR LED (ADA388, 940 nm) [chain two together for better signal]
- 2N2222A NPN transistor
- 33 Ω resistor (LED current limiter)
- 1 kΩ resistor (transistor base)
- 100 nF ceramic capacitor (decoupling, optional but recommended)

**Why GPIO 12?** The Waveshare audio HAT uses I2S, which occupies GPIO 18 (BCLK) — the usual hardware PWM0 pin. GPIO 12 is the alternate hardware PWM0 mapping and is free.

### Wiring

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

### System Configuration

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

Create a udev rule:

```bash
echo 'SUBSYSTEM=="lirc", MODE="0660", GROUP="pi"' | sudo tee /etc/udev/rules.d/99-lirc.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

**3. Install `ir-keytable`** (included in `make setup`, or install manually):

```bash
sudo apt install -y ir-keytable
```

### Discovering Your Sony SIRC Scancode

You need the scancode for the input button on your specific Sony stereo. The easiest way is to decode your existing remote:

1. Wire a TSOP38238 or similar IR receiver to the Pi (data pin → any GPIO, e.g. GPIO 23).
2. Enable the receiver overlay temporarily and run:
   ```bash
   sudo ir-keytable -p sony -t
   ```
3. Press the **input select** button on your Sony remote and read the reported scancode from the output, e.g. `SONY12:0x015`.

Alternatively, search the LIRC remote database for your model:  
`https://lirc.sourceforge.net/remotes/sony/`

### Configuring the Scancode

Copy the example config and fill in your values:

```bash
cp ir_config.json.example ir_config.json
```

`ir_config.json` is gitignored so it stays local to each device.

```json
{
  "input": {
    "protocol": "SONY12",
    "scancode": "0x812",
    "switch_delay_s": 0.5
  },
  "volume_up": {
    "protocol": "SONY12",
    "scancode": "0x000"
  }
}
```

Each key is a named command. Per-command fields:

- **`protocol`** — IR protocol, e.g. `SONY12`, `NEC`, `RC5`. Defaults to `SONY12` if omitted.
- **`scancode`** — hex scancode for the button. See discovery steps above.
- **`repeat`** — number of times to send the frame. SIRC (Sony) requires `3`; most other protocols require `1`. Defaults to `1` if omitted.
- **`switch_delay_s`** — seconds to wait after sending the command. Useful for `input` to give the stereo time to switch. Omit or set to `0` for no delay.

The `input` key is what the server sends before starting playback. All other keys are available for future endpoints via `ir_blaster.send_command("key")`.

If `ir_config.json` does not exist, or a requested key is absent, IR blasting is silently skipped and playback continues normally.

### Testing from the Command Line

Before relying on the server, verify the circuit works. Substitute the scancode from your `ir_config.json`:

```bash
# Send the input-select command 3 times (SIRC requirement)
for i in 1 2 3; do
    ir-ctl -d /dev/lirc0 --scancode SONY12:0x812
    sleep 0.05
done
```

The stereo should switch inputs.

### Quick Play

`quickplay.json` contains a list of artist/album targets for the `/quickplay/{number}` endpoint. An example is committed to the repo. To customize it locally without your changes being picked up by git, run:

```bash
git update-index --skip-worktree quickplay.json
```

To commit a deliberate update to the example, reverse that first:

```bash
git update-index --no-skip-worktree quickplay.json
```
