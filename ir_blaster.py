import logging
import subprocess
import time
from pathlib import Path

import config
import stereo_sensor

logger = logging.getLogger(__name__)

LIRC_DEVICE = "/dev/lirc0"


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


def send_command(key: str) -> None:
    """Send the named IR command from the ir section of piserver.json."""
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

    if delay:
        time.sleep(delay)


def power_on_stereo() -> None:
    """Send the power-on IR command if the sensor indicates the stereo is off.

    Silently skips if use_sensor is not enabled in piserver.json, or if the
    sensor is unavailable. The 'power' IR command is also silently skipped if
    absent from config.
    """
    if not config.load().get("use_sensor"):
        return
    if stereo_sensor.is_on() is False:
        logger.info("ir_blaster: stereo is off — sending power command")
        send_command("power")


def select_stereo_input() -> None:
    power_on_stereo()
    ir_config = config.load().get("ir", [])
    item = next((item for item in ir_config if item.get("default")), None)
    if item:
        send_command(item["name"])
