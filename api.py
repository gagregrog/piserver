import logging
import subprocess

from fastapi import APIRouter, HTTPException
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

    `on` is the photoresistor sensor reading: true (LED lit), false (dark), or
    null when the sensor is unavailable (no gpiozero / pin can't be opened).
    `sensor_enabled` reflects the `use_sensor` config flag — when false, the
    auto power-on logic ignores the sensor, so `on` is informational only.
    """
    on = stereo_sensor.is_on()
    logger.info("Stereo status requested -> on=%s", on)
    return {"on": on, "sensor_enabled": bool(config.load().get("use_sensor"))}


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
    return [{"name": item.get("name", ""), "class": item.get("class", "")} for item in ir_config]


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


@router.post("/service/mopidy/restart")
def restart_mopidy():
    logger.info("Mopidy restart requested")
    result = subprocess.run(
        ["sudo", "systemctl", "restart", "mopidy"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        if "is not allowed" in result.stderr or "password is required" in result.stderr:
            raise HTTPException(
                status_code=401,
                detail="Permission denied. The pi user needs passwordless sudo for 'systemctl restart mopidy'. See README for setup instructions."
            )
        raise HTTPException(status_code=500, detail=result.stderr or "Failed to restart mopidy")
    logger.info("Mopidy restarted successfully")
    return {"status": "restarted"}
