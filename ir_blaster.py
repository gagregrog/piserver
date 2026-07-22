import logging
import subprocess
import threading
import time
from pathlib import Path

import config
import stereo_sensor

logger = logging.getLogger(__name__)

LIRC_DEVICE = "/dev/lirc0"

# Serializes access to the single IR blaster. Endpoints run in a threadpool and
# volume floor/startup now run as background tasks, so two IR streams could
# otherwise interleave on the LIRC device and corrupt each other. Reentrant so a
# compound action (which holds the lock) can call send_command (which re-takes
# it) on the same thread.
_ir_lock = threading.RLock()


def _read_sirc(sirc: dict) -> tuple[int, int]:
    """Extract (address, command) from a sirc config dict. Values may be ints or hex strings."""
    def _coerce(v: int | str, field: str) -> int:
        if isinstance(v, int):
            return v
        try:
            return int(v, 0)
        except (ValueError, TypeError):
            raise ValueError(f"sirc.{field} must be an integer or hex string, got {v!r}")

    return _coerce(sirc["address"], "address"), _coerce(sirc["command"], "command")


def _sirc_protocol(address: int) -> str:
    """Select the correct Sony SIRC variant based on address width."""
    if address <= 0x1F:
        return "sony12"
    if address <= 0xFF:
        return "sony15"
    raise ValueError(f"address 0x{address:x} exceeds 8-bit SIRC-15 range")


def send_command(key: str, count: int = 1) -> None:
    """Send the named IR command from the ir section of piserver.json.

    count is the number of discrete presses to send (e.g. 3 volume increments).
    Each press is a full SIRC burst (the command's configured `repeat` frames)
    followed by the command's `delay`, so the receiver registers them as
    separate presses rather than one held button.
    """
    ir_config = config.load().get("ir")
    if not ir_config:
        return
    cmd = next((item for item in ir_config if item.get("name") == key), None)
    if not cmd or not cmd.get("sirc"):
        return

    if not Path(LIRC_DEVICE).exists():
        logger.warning(
            "ir_blaster: %s not found — is the gpio-ir-tx overlay enabled?",
            LIRC_DEVICE,
        )
        return

    repeat = cmd.get("repeat", 1)
    delay = cmd.get("delay", 0)

    try:
        address, command = _read_sirc(cmd["sirc"])
    except (KeyError, ValueError) as e:
        logger.warning("ir_blaster: %s", e)
        return

    try:
        protocol = _sirc_protocol(address)
    except ValueError as e:
        logger.warning("ir_blaster: %s", e)
        return

    # The kernel encodes Sony scancodes as (address << 16) | command
    scancode = (address << 16) | command

    # Hold the blaster for the whole burst so concurrent senders don't interleave.
    with _ir_lock:
        for press in range(max(count, 1)):
            for i in range(repeat):
                result = subprocess.run(
                    ["ir-ctl", "-d", LIRC_DEVICE, "--scancode", f"{protocol}:{scancode:#x}"],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logger.warning("ir_blaster: send failed: %s", result.stderr.strip())
                    return
                if i < repeat - 1:
                    time.sleep(0.045)

            logger.info(
                "ir_blaster: sent %s A:0x%02x C:0x%02x x%d (key=%r)",
                protocol, address, command, repeat, key,
            )

            # Gap between presses so each burst registers separately.
            if delay:
                time.sleep(delay)


def power_on_stereo() -> bool:
    """Send the power-on IR command if the sensor indicates the stereo is off.

    Returns True if a power-on command was actually sent (i.e. the stereo was
    off). Silently returns False if the stereo sensor is not enabled in
    piserver.json, if the sensor is unavailable, or if the stereo is already on.
    The 'power' IR command is also silently skipped if absent from config.
    """
    if not stereo_sensor.is_enabled():
        return False
    if stereo_sensor.is_on() is False:
        logger.info("ir_blaster: stereo is off — sending power command")
        send_command("power")
        return True
    return False


def floor_volume() -> bool:
    """Drive the receiver's volume to zero.

    Sends the configured `down` command `floor_presses` times; the receiver
    clamps at zero regardless of where it started. Each command's own `delay`
    paces the discrete presses so they all register. Returns True if a command
    was sent, False when the `volume` block is absent or misconfigured.
    """
    vol = config.load().get("volume")
    if not vol:
        return False
    down = vol.get("down")
    if not down:
        logger.warning("ir_blaster: volume block missing 'down' — cannot floor volume")
        return False
    floor = vol.get("floor_presses", 50)
    logger.info("ir_blaster: floor volume — %dx %s", floor, down)
    with _ir_lock:
        send_command(down, count=floor)
    return True


def apply_startup_volume() -> bool:
    """Drive the receiver to the configured target volume.

    The receiver only exposes relative volume, so we floor it (see floor_volume)
    then step up to the configured level — giving a deterministic absolute
    volume from any starting point. Returns True if commands were sent, False
    when the `volume` block is absent or misconfigured. Run on a cold start (see
    select_stereo_input) and on demand via POST /volume/startup.
    """
    # Atomic across floor + step-up so a concurrent request can't land presses
    # in the middle and throw off the resulting level.
    with _ir_lock:
        if not floor_volume():
            return False
        vol = config.load().get("volume")
        up = vol.get("up")
        if not up:
            logger.warning("ir_blaster: volume block missing 'up' — skipping startup step-up")
            return False
        presses = vol.get("startup_presses", 15)
        logger.info("ir_blaster: startup volume — %dx %s", presses, up)
        send_command(up, count=presses)
    return True


def shutdown_stereo() -> None:
    """Floor the volume, then power the receiver off — in that order.

    Run as a background task so the caller (e.g. the controller's stop-hold)
    returns immediately while the receiver comes down quietly before power-off.
    """
    with _ir_lock:
        floor_volume()
        logger.info("ir_blaster: powering off receiver")
        send_command("power")


def select_stereo_input() -> None:
    # Capture whether we actually powered the stereo on from off, so the volume
    # is normalized only on a genuine cold start — never mid-session, which
    # would jarringly reset the volume on every play.
    powered_on = power_on_stereo()
    ir_config = config.load().get("ir", [])
    item = next((item for item in ir_config if item.get("default")), None)
    if item:
        send_command(item["name"])
    if powered_on:
        apply_startup_volume()
