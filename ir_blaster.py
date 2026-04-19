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


def send_command(key: str) -> None:
    """Send the named IR command from ir_config.json.

    Silently skips if the config file is absent, the key is not present,
    or the key's entry is missing a scancode.
    """
    config = _load_config()
    if config is None:
        return
    cmd = config.get(key)
    if not cmd or not cmd.get("scancode"):
        return

    if not Path(LIRC_DEVICE).exists():
        logger.warning(
            "ir_blaster: %s not found — is the gpio-ir-tx overlay enabled?",
            LIRC_DEVICE,
        )
        return

    protocol = cmd.get("protocol", "SONY12")
    scancode = cmd["scancode"]
    repeat = cmd.get("repeat", 1)
    delay = cmd.get("switch_delay_s", 0)

    for i in range(repeat):
        result = subprocess.run(
            ["ir-ctl", "-d", LIRC_DEVICE, "--scancode", f"{protocol}:{scancode}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning("ir_blaster: send failed: %s", result.stderr.strip())
            return
        if i < repeat - 1:
            time.sleep(0.045)  # 45 ms between frames

    if delay:
        time.sleep(delay)

    logger.info("ir_blaster: sent %s:%s x%d (key=%r)", protocol, scancode, repeat, key)


def select_stereo_input() -> None:
    send_command("input")
