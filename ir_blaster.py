import json
import logging
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

LIRC_DEVICE = "/dev/lirc0"
CONFIG_FILE = Path(__file__).parent / "ir_config.json"


def _load_config() -> dict | None:
    if not CONFIG_FILE.exists():
        return None
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception as e:
        logger.warning("ir_blaster: could not read config: %s", e)
        return None


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


def send_command(key: str) -> None:
    """Send the named IR command from ir_config.json.

    Silently skips if the config file is absent or the key is not present.
    Config entries use a 'sirc' dict, e.g.:
        {"input": {"sirc": {"address": "0x10", "command": "0x12"}, "repeat": 3}}
    """
    config = _load_config()
    if config is None:
        return
    cmd = config.get(key)
    if not cmd or not cmd.get("sirc"):
        return

    if not Path(LIRC_DEVICE).exists():
        logger.warning(
            "ir_blaster: %s not found — is the gpio-ir-tx overlay enabled?",
            LIRC_DEVICE,
        )
        return

    repeat = cmd.get("repeat", 1)
    delay = cmd.get("switch_delay_s", 0)

    try:
        address, command = _read_sirc(cmd["sirc"])
    except (KeyError, ValueError) as e:
        logger.warning("ir_blaster: %s", e)
        return

    # The kernel encodes Sony scancodes as (address << 16) | command
    scancode = (address << 16) | command

    for i in range(repeat):
        result = subprocess.run(
            ["ir-ctl", "-d", LIRC_DEVICE, "--scancode", f"sony12:{scancode:#x}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("ir_blaster: send failed: %s", result.stderr.strip())
            return
        if i < repeat - 1:
            time.sleep(0.045)

    logger.info(
        "ir_blaster: sent sony12 A:0x%02x C:0x%02x x%d (key=%r)",
        address, command, repeat, key,
    )

    if delay:
        time.sleep(delay)


def select_stereo_input() -> None:
    send_command("input")
