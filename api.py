import json
import logging
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import play_service
import player

QUICKPLAY_FILE = Path(__file__).parent / "quickplay.json"

logger = logging.getLogger(__name__)

router = APIRouter()


class QuickplayEntry(BaseModel):
    artist: str | None = None
    album: str | None = None
    shuffle: bool = False


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


@router.get("/quickplay")
def get_quickplay():
    logger.info("Getting quickplay list")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    return {"quickplay": entries}


@router.get("/quickplay/{index}")
def get_quickplay_entry(index: int):
    logger.info(f"Getting quickplay entry {index}")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    return {"index": index, **entries[index]}


@router.put("/quickplay")
def replace_quickplay(body: list[QuickplayEntry]):
    logger.info(f"Replacing quickplay list ({len(body)} entries)")
    try:
        for e in body:
            player.validate_entry(e.artist, e.album, e.shuffle)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    data = [e.model_dump() for e in body]
    QUICKPLAY_FILE.write_text(json.dumps(data, indent=2))
    return {"quickplay": data}


@router.put("/quickplay/{index}")
def update_quickplay_entry(index: int, body: QuickplayEntry):
    label = "shuffle all" if body.shuffle else (f"{body.artist}" + (f" / {body.album}" if body.album else ""))
    logger.info(f"Updating quickplay entry {index}: {label}")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index > len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    try:
        player.validate_entry(body.artist, body.album, body.shuffle)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if index == len(entries):
        entries.append(body.model_dump())
    else:
        entries[index] = body.model_dump()
    QUICKPLAY_FILE.write_text(json.dumps(entries, indent=2))
    return {"index": index, **entries[index]}


@router.post("/quickplay/{index}")
def quickplay(index: int):
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    entry = entries[index]
    artist = entry.get("artist")
    album = entry.get("album")
    shuffle = entry.get("shuffle", False)
    if shuffle:
        logger.info(f"Quickplay {index}: shuffle all")
        play_service.shuffle_all()
        return {"status": "playing", "shuffle": True}
    logger.info(f"Quickplay {index}: {artist}" + (f" / {album}" if album else " (all albums)"))
    try:
        if album:
            play_service.play_album(artist, album)
        else:
            play_service.play_artist(artist)
    except player.NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    result = {"status": "playing", "artist": artist}
    if album:
        result["album"] = album
    return result


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
