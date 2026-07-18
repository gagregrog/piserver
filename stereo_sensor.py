import logging

import config

logger = logging.getLogger(__name__)

# Read the LDR divider voltage via an ADS1115 ADC over I2C and apply software
# on/off thresholds with hysteresis. The Pi has no analog input, so the ADS1115
# is required for LDR sensing.
DEFAULT_ADS_ADDRESS = 0x48
DEFAULT_ADS_CHANNEL = 0        # A0..A3
DEFAULT_ADS_GAIN = 1           # PGA: 2/3, 1, 2, 4, 8, 16 (FS ±6.144V..±0.256V)
DEFAULT_ON_THRESHOLD = 1.8     # volts: reading >= this => ON
DEFAULT_OFF_THRESHOLD = 1.5    # volts: reading <= this => OFF (band = hysteresis)

# ── Lazily-initialized hardware handle ───────────────────────────────────────
_ads_channel = None               # adafruit_ads1x15 AnalogIn
_ads_init_attempted = False
_hysteresis_on = None             # last resolved ON/OFF state (hysteresis)


def _cfg() -> dict:
    return config.load().get("stereo_sensor", {}) or {}


def is_enabled() -> bool:
    """Whether the stereo sensor is enabled (stereo_sensor.enabled in config).

    When disabled, the auto power-on logic ignores the sensor; the /stereo
    endpoint still reports the raw reading for informational purposes.
    """
    return bool(_cfg().get("enabled"))


def _as_int(value, default: int) -> int:
    """Accept an int or a hex/decimal string (e.g. 72 or "0x48")."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value), 0)
    except (TypeError, ValueError):
        logger.warning("stereo_sensor: bad int value %r, using %r", value, default)
        return default


def _init_ads() -> None:
    global _ads_channel
    cfg = _cfg()
    address = _as_int(cfg.get("address"), DEFAULT_ADS_ADDRESS)
    channel = _as_int(cfg.get("channel"), DEFAULT_ADS_CHANNEL)
    gain = cfg.get("gain", DEFAULT_ADS_GAIN)
    try:
        import board  # type: ignore[import]
        import busio  # type: ignore[import]
        import adafruit_ads1x15.ads1115 as ADS  # type: ignore[import]
        from adafruit_ads1x15.analog_in import AnalogIn  # type: ignore[import]

        if channel < 0 or channel > 3:
            logger.warning("stereo_sensor: bad ADS channel %r, using 0", channel)
            channel = 0
        i2c = busio.I2C(board.SCL, board.SDA)
        ads = ADS.ADS1115(i2c, address=address)
        ads.gain = gain
        _ads_channel = AnalogIn(ads, channel)
        logger.info(
            "stereo_sensor: ADS1115 at 0x%02x channel A%d gain %s",
            address, channel, gain,
        )
    except Exception as e:
        logger.warning("stereo_sensor: could not configure ADS1115: %s", e)


def read_voltage() -> float | None:
    """Return the ADS1115 channel voltage, or None if the ADC is unavailable.

    Returns None when the adafruit libraries are missing (e.g. on a dev machine)
    or the device can't be reached.
    """
    global _ads_init_attempted
    if not _ads_init_attempted:
        _ads_init_attempted = True
        _init_ads()
    if _ads_channel is None:
        return None
    try:
        return float(_ads_channel.voltage)
    except Exception as e:
        logger.warning("stereo_sensor: ADS1115 read failed: %s", e)
        return None


def _resolve_state(voltage: float | None) -> bool | None:
    """Map a voltage to ON/OFF with hysteresis. Holds the previous state while
    the reading sits inside the [off_threshold, on_threshold] deadband."""
    global _hysteresis_on
    if voltage is None:
        return None
    cfg = _cfg()
    on_t = float(cfg.get("on_threshold", DEFAULT_ON_THRESHOLD))
    off_t = float(cfg.get("off_threshold", DEFAULT_OFF_THRESHOLD))
    if voltage >= on_t:
        _hysteresis_on = True
    elif voltage <= off_t:
        _hysteresis_on = False
    elif _hysteresis_on is None:
        # Cold start inside the deadband — resolve against the midpoint so the
        # first reading is still deterministic.
        _hysteresis_on = voltage >= (on_t + off_t) / 2
    # else: inside the band with a known state — hold it (hysteresis).
    return _hysteresis_on


def is_on() -> bool | None:
    """Return True if the stereo is detected on, False if off, None if the
    sensor is unavailable.

    Reads the LDR divider voltage via the ADS1115 and applies the configured
    on/off thresholds (`stereo_sensor.on_threshold` / `off_threshold`) with
    hysteresis.
    """
    return _resolve_state(read_voltage())
