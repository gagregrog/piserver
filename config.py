import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_FILE = Path(__file__).parent / "piserver.json"


def load() -> dict:
    """Load piserver.json. Returns an empty dict if the file is absent or unreadable."""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text())
    except Exception as e:
        logger.warning("config: could not read %s: %s", CONFIG_FILE, e)
        return {}


def save(data: dict) -> None:
    """Write data to piserver.json."""
    CONFIG_FILE.write_text(json.dumps(data, indent=2))
