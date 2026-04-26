import logging

logger = logging.getLogger(__name__)

GPIO_PIN = 17

_device = None
_device_init_attempted = False


def is_on() -> bool | None:
    """Return True if the stereo LED is detected as on, False if off, None if sensor unavailable.

    Uses a lazily-initialized gpiozero.DigitalInputDevice on GPIO 17. Returns None if
    gpiozero is not installed (e.g. running on a dev machine) or the pin cannot be opened.
    """
    global _device, _device_init_attempted
    if not _device_init_attempted:
        _device_init_attempted = True
        try:
            from gpiozero import DigitalInputDevice  # type: ignore[import]
            _device = DigitalInputDevice(GPIO_PIN, pull_up=False)
            logger.info("stereo_sensor: configured on GPIO %d", GPIO_PIN)
        except Exception as e:
            logger.warning("stereo_sensor: could not configure GPIO %d: %s", GPIO_PIN, e)

    if _device is None:
        return None
    try:
        return bool(_device.value)
    except Exception as e:
        logger.warning("stereo_sensor: read failed: %s", e)
        return None
