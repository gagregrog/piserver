import logging
import subprocess

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

import config
import ir_blaster
import play_service
import player
import stereo_sensor

logger = logging.getLogger(__name__)

router = APIRouter()


class QuickplayItem(BaseModel):
    artist: str | None = None
    album: str | None = None


class QuickplayEntry(BaseModel):
    # A shuffle-all entry (whole library, randomized) OR a sequential list of
    # items. When shuffle is true, items is ignored.
    shuffle: bool = False
    items: list[QuickplayItem] = []


class StereoConfig(BaseModel):
    # Every field is optional; only the ones sent are merged into the
    # stereo_sensor config block. address accepts an int or a hex string
    # ("0x48").
    enabled: bool | None = None
    address: str | int | None = None
    channel: int | None = None
    gain: int | None = None
    on_threshold: float | None = None
    off_threshold: float | None = None


def _item_label(item: QuickplayItem) -> str:
    return f"{item.artist}" + (f" / {item.album}" if item.album else "")


def _entry_label(entry: QuickplayEntry) -> str:
    if entry.shuffle:
        return "shuffle all"
    if not entry.items:
        return "(empty)"
    return ", ".join(_item_label(i) for i in entry.items)


@router.post("/play")
def play():
    logger.info("Play/pause command received")
    return {"status": play_service.toggle_play()}


@router.post("/shuffle")
def shuffle_all():
    logger.info("Shuffling all tracks")
    play_service.shuffle_all()
    return {"status": "playing", "shuffle": True}


@router.post("/stop")
def stop():
    logger.info("Stop command received")
    player.stop()
    return {"status": "stopped"}


@router.post("/next")
def next_track():
    logger.info("Next track command received")
    player.next_track()
    return {"status": "next"}


@router.post("/previous")
def previous_track():
    logger.info("Previous track command received")
    player.previous_track()
    return {"status": "previous"}


@router.post("/restart")
def restart_track():
    logger.info("Restart track command received")
    player.restart_track()
    return {"status": "restarted"}


@router.get("/current")
def current_track():
    logger.info("Current track requested")
    return player.current_track()


@router.get("/stereo")
def stereo_status():
    """Report whether the system thinks the stereo is powered on.

    `on` is the sensor reading: true (LED lit), false (dark), or null when the
    sensor is unavailable. `voltage` is the raw ADS1115 reading in volts (null
    if the ADC is unavailable) — handy for tuning thresholds from the web UI.
    `sensor_enabled` reflects the `stereo_sensor.enabled` config flag — when
    false, the auto power-on logic ignores the sensor, so `on` is informational
    only.
    """
    on = stereo_sensor.is_on()
    voltage = stereo_sensor.read_voltage()
    logger.info("Stereo status requested -> on=%s v=%s", on, voltage)
    return {
        "on": on,
        "voltage": voltage,
        "sensor_enabled": stereo_sensor.is_enabled(),
    }


@router.get("/stereo/config")
def get_stereo_config():
    """Return the current stereo_sensor config block with defaults applied.

    Used by the web UI to populate the sensor configuration form. `address` is
    normalized to a hex string for display.
    """
    cfg = stereo_sensor._cfg()
    address = cfg.get("address", stereo_sensor.DEFAULT_ADS_ADDRESS)
    if isinstance(address, int):
        address = f"0x{address:02x}"
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "address": address,
        "channel": cfg.get("channel", stereo_sensor.DEFAULT_ADS_CHANNEL),
        "gain": cfg.get("gain", stereo_sensor.DEFAULT_ADS_GAIN),
        "on_threshold": cfg.get("on_threshold", stereo_sensor.DEFAULT_ON_THRESHOLD),
        "off_threshold": cfg.get("off_threshold", stereo_sensor.DEFAULT_OFF_THRESHOLD),
    }


@router.put("/stereo/config")
def update_stereo_config(body: StereoConfig):
    """Merge the provided fields into the stereo_sensor config block and persist.

    Re-initializes the ADC afterwards so hardware changes (address / channel /
    gain) take effect immediately without a service restart. Returns the updated
    block.
    """
    updates = body.model_dump(exclude_none=True)
    logger.info("Updating stereo_sensor config: %s", updates)
    cfg = config.load()
    sensor = dict(cfg.get("stereo_sensor") or {})
    sensor.update(updates)
    cfg["stereo_sensor"] = sensor
    config.save(cfg)
    # Re-ingest: drop the cached ADC handle so the next read reconfigures with
    # the new address / channel / gain.
    stereo_sensor.reset()
    return {"stereo_sensor": sensor}


@router.post("/stereo/sample")
def stereo_sample(count: int = stereo_sensor.DEFAULT_SAMPLE_COUNT):
    """Take a burst of ADC readings and return summary stats without writing
    anything.

    The web UI runs this once per state (stereo off / on) and lets the user
    apply a suggested threshold to the on/off slot before saving.
    """
    count = max(1, min(count, 500))
    logger.info("Stereo sample requested (count=%d)", count)
    result = stereo_sensor.sample(count)
    if result is None:
        raise HTTPException(status_code=503, detail="stereo sensor unavailable")
    return result


@router.get("/queue")
def get_queue():
    logger.info("Queue requested")
    return {"queue": player.get_queue()}


@router.post("/playlist/{name}")
def load_playlist(name: str):
    logger.info(f"Loading playlist: {name}")
    play_service.load_playlist(name)
    return {"status": "loaded", "playlist": name}


@router.get("/albums")
def list_albums():
    logger.info("Listing albums")
    return {"albums": player.list_albums()}


@router.get("/artists")
def list_artists():
    logger.info("Listing artists")
    return {"artists": player.list_artists()}


@router.get("/artist/{name}/albums")
def list_artist_albums(name: str):
    logger.info(f"Listing albums for artist: {name}")
    try:
        return {"artist": name, "albums": player.list_artist_albums(name)}
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/artist/{artist}")
def play_artist(artist: str):
    logger.info(f"Playing all albums for artist: {artist}")
    try:
        play_service.play_artist(artist)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "playing", "artist": artist}


@router.post("/artist/{artist}/album/{album}")
def play_album(artist: str, album: str):
    logger.info(f"Playing album: {artist} / {album}")
    try:
        play_service.play_album(artist, album)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"status": "playing", "artist": artist, "album": album}


@router.get("/ir")
def list_ir_functions():
    ir_config = config.load().get("ir", [])
    return [
        {
            "name": item.get("name", ""),
            # Human-friendly label for the UI; falls back to the raw name.
            "label": item.get("label") or item.get("name", ""),
            "class": item.get("class", ""),
            # When true, the UI renders a shared increment stepper for this
            # command's class and sends the chosen value as `count`.
            "qty": bool(item.get("qty", False)),
            # When true, the UI renders a "Floor" button for this command's
            # class that triggers POST /volume/floor.
            "floor": bool(item.get("floor", False)),
            # When true, the UI renders a "Target" button for this command's
            # class that triggers POST /volume/startup.
            "startup": bool(item.get("startup", False)),
        }
        for item in ir_config
    ]


@router.post("/volume/floor", status_code=202)
def volume_floor(background_tasks: BackgroundTasks):
    """Drive the receiver's volume to zero using the `volume` policy block.

    Flooring sends dozens of spaced IR presses (several seconds), so the send
    runs in the background and the request returns immediately — the client
    should not hold the connection open for the whole burst.
    """
    logger.info("Volume floor requested")
    vol = config.load().get("volume") or {}
    if not vol.get("down"):
        raise HTTPException(status_code=404, detail="volume floor not configured")
    background_tasks.add_task(ir_blaster.floor_volume)
    return {"status": "flooring"}


@router.post("/volume/startup", status_code=202)
def volume_startup(background_tasks: BackgroundTasks):
    """Drive the receiver to the configured target volume (floor, then step up).

    Runs in the background (see /volume/floor) and returns immediately.
    """
    logger.info("Volume startup (target level) requested")
    vol = config.load().get("volume") or {}
    if not (vol.get("down") and vol.get("up")):
        raise HTTPException(status_code=404, detail="volume startup not configured")
    background_tasks.add_task(ir_blaster.apply_startup_volume)
    return {"status": "normalizing"}


@router.post("/stereo/off", status_code=202)
def stereo_off(background_tasks: BackgroundTasks):
    """Floor the volume, then power the receiver off — in that order.

    Runs in the background and returns immediately so the controller's stop-hold
    doesn't block while the volume floors before power-off.
    """
    logger.info("Stereo off requested (floor, then power off)")
    background_tasks.add_task(ir_blaster.shutdown_stereo)
    return {"status": "powering off"}


@router.post("/ir/{function}")
def send_ir(function: str, count: int = 1):
    ir_config = config.load().get("ir", [])
    if not any(item.get("name") == function for item in ir_config):
        raise HTTPException(status_code=404, detail=f"IR function {function!r} not found")
    if count < 1:
        count = 1
    logger.info(f"IR command: {function} x{count}")
    ir_blaster.send_command(function, count=count)
    return {"sent": function, "count": count}


@router.get("/quickplay")
def get_quickplay():
    logger.info("Getting quickplay list")
    entries = config.load().get("quickplay", [])
    return {"quickplay": entries}


@router.get("/quickplay/{index}")
def get_quickplay_entry(index: int):
    logger.info(f"Getting quickplay entry {index}")
    entries = config.load().get("quickplay", [])
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    return {"index": index, **entries[index]}


@router.put("/quickplay")
def replace_quickplay(body: list[QuickplayEntry]):
    logger.info(f"Replacing quickplay list ({len(body)} entries)")
    try:
        for entry in body:
            if entry.shuffle:
                continue
            for item in entry.items:
                player.validate_entry(item.artist, item.album)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    data = [e.model_dump() for e in body]
    cfg = config.load()
    cfg["quickplay"] = data
    config.save(cfg)
    return {"quickplay": data}


@router.put("/quickplay/{index}")
def update_quickplay_entry(index: int, body: QuickplayEntry):
    logger.info(f"Updating quickplay entry {index}: {_entry_label(body)}")
    cfg = config.load()
    entries = cfg.get("quickplay", [])
    if index < 0 or index > len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    try:
        if not body.shuffle:
            for item in body.items:
                player.validate_entry(item.artist, item.album)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if index == len(entries):
        entries.append(body.model_dump())
    else:
        entries[index] = body.model_dump()
    cfg["quickplay"] = entries
    config.save(cfg)
    return {"index": index, **entries[index]}


@router.post("/quickplay/{index}")
def quickplay(index: int):
    logger.info(f"Quickplay {index}")
    try:
        return play_service.play_quickplay(index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _run_sudo(args: list[str], what: str) -> None:
    """Run a passwordless-sudo command, raising HTTPException on failure.

    Maps a missing sudoers rule to 401 (actionable) and any other failure to
    500. See the README for the passwordless-sudo setup the pi user needs.
    """
    result = subprocess.run(["sudo", *args], capture_output=True, text=True)
    if result.returncode != 0:
        if "is not allowed" in result.stderr or "password is required" in result.stderr:
            raise HTTPException(
                status_code=401,
                detail=f"Permission denied. The pi user needs passwordless sudo for '{' '.join(args)}'. See README for setup instructions."
            )
        raise HTTPException(status_code=500, detail=result.stderr or f"Failed to {what}")


@router.post("/service/mopidy/restart")
def restart_mopidy():
    logger.info("Mopidy restart requested")
    _run_sudo(["systemctl", "restart", "mopidy"], "restart mopidy")
    logger.info("Mopidy restarted successfully")
    return {"status": "restarted"}


@router.post("/system/reboot")
def system_reboot():
    logger.info("Raspberry Pi reboot requested")
    _run_sudo(["systemctl", "reboot"], "reboot")
    return {"status": "rebooting"}


@router.post("/system/shutdown")
def system_shutdown():
    logger.info("Raspberry Pi shutdown requested")
    _run_sudo(["systemctl", "poweroff"], "shut down")
    return {"status": "shutting down"}
