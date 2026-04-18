import json
import logging
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter, HTTPException
from mpd import MPDClient, CommandError
from pydantic import BaseModel

QUICKPLAY_FILE = Path(__file__).parent / "quickplay.json"

logger = logging.getLogger(__name__)

router = APIRouter()


@contextmanager
def mpd_connection():
    client = MPDClient()
    client.connect("localhost", 6600)
    try:
        yield client
    finally:
        client.disconnect()


class QuickplayEntry(BaseModel):
    artist: str | None = None
    album: str | None = None
    shuffle: bool = False


def _validate_entry(mpd, artist: str | None, album: str | None, shuffle: bool = False):
    if shuffle:
        return
    if album is not None:
        path = f"Subsonic/Artists/{artist}/{album}"
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise HTTPException(status_code=404, detail=f"Album not found: {artist} / {album}")
        if not entries:
            raise HTTPException(status_code=404, detail=f"Album is empty: {artist} / {album}")
    else:
        path = f"Subsonic/Artists/{artist}"
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise HTTPException(status_code=404, detail=f"Artist not found: {artist}")
        if not [e for e in entries if "directory" in e]:
            raise HTTPException(status_code=404, detail=f"No albums found for artist: {artist}")


@router.post("/play")
def play():
    logger.info("Play/pause command received")
    with mpd_connection() as mpd:
        state = mpd.status()["state"]
        if state == "play":
            mpd.pause(1)
            return {"status": "paused"}
        elif state == "pause":
            mpd.pause(0)
            return {"status": "playing"}
        else:
            mpd.play()
            return {"status": "playing"}


@router.post("/shuffle")
def shuffle_all():
    logger.info("Shuffling all tracks")
    with mpd_connection() as mpd:
        mpd.clear()
        mpd.add("Subsonic/Albums")
        mpd.shuffle()
        mpd.play()
    return {"status": "playing", "shuffle": True}


@router.post("/stop")
def stop():
    logger.info("Stop command received")
    with mpd_connection() as mpd:
        mpd.stop()
    return {"status": "stopped"}


@router.post("/next")
def next_track():
    logger.info("Next track command received")
    with mpd_connection() as mpd:
        mpd.next()
    return {"status": "next"}


@router.post("/previous")
def previous_track():
    logger.info("Previous track command received")
    with mpd_connection() as mpd:
        mpd.previous()
    return {"status": "previous"}


@router.post("/restart")
def restart_track():
    logger.info("Restart track command received")
    with mpd_connection() as mpd:
        mpd.seekcur(0)
    return {"status": "restarted"}


@router.get("/current")
def current_track():
    logger.info("Current track requested")
    with mpd_connection() as mpd:
        status = mpd.status()
        song = mpd.currentsong()
    return {"status": status["state"], "track": song}


@router.get("/queue")
def get_queue():
    logger.info("Queue requested")
    with mpd_connection() as mpd:
        queue = mpd.playlistinfo()
    return {"queue": queue}


@router.post("/playlist/{name}")
def load_playlist(name: str):
    logger.info(f"Loading playlist: {name}")
    with mpd_connection() as mpd:
        mpd.clear()
        mpd.load(name)
        mpd.play()
    return {"status": "loaded", "playlist": name}


@router.get("/albums")
def list_albums():
    logger.info("Listing albums")
    with mpd_connection() as mpd:
        entries = mpd.lsinfo("Subsonic/Albums")
    albums = [e["directory"].split("/")[-1] for e in entries if "directory" in e]
    return {"albums": albums}


@router.get("/artists")
def list_artists():
    logger.info("Listing artists")
    with mpd_connection() as mpd:
        entries = mpd.lsinfo("Subsonic/Artists")
    artists = [e["directory"].split("/")[-1] for e in entries if "directory" in e]
    return {"artists": artists}


@router.get("/artist/{name}/albums")
def list_artist_albums(name: str):
    logger.info(f"Listing albums for artist: {name}")
    path = f"Subsonic/Artists/{name}"
    with mpd_connection() as mpd:
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise HTTPException(status_code=404, detail=f"Artist not found: {name}")
    albums = [e["directory"].split("/")[-1] for e in entries if "directory" in e]
    if not albums:
        raise HTTPException(status_code=404, detail=f"No albums found for artist: {name}")
    return {"artist": name, "albums": albums}


@router.post("/artist/{artist}")
def play_artist(artist: str):
    logger.info(f"Playing all albums for artist: {artist}")
    path = f"Subsonic/Artists/{artist}"
    with mpd_connection() as mpd:
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise HTTPException(status_code=404, detail=f"Artist not found: {artist}")
        if not [e for e in entries if "directory" in e]:
            raise HTTPException(status_code=404, detail=f"No albums found for artist: {artist}")
        mpd.clear()
        mpd.add(path)
        mpd.play()
    return {"status": "playing", "artist": artist}


@router.post("/artist/{artist}/album/{album}")
def play_album(artist: str, album: str):
    logger.info(f"Playing album: {artist} / {album}")
    path = f"Subsonic/Artists/{artist}/{album}"
    with mpd_connection() as mpd:
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise HTTPException(status_code=404, detail=f"Album not found: {album}")
        if not entries:
            raise HTTPException(status_code=404, detail=f"Album is empty: {album}")
        mpd.clear()
        mpd.add(path)
        mpd.play()
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
    with mpd_connection() as mpd:
        for e in body:
            _validate_entry(mpd, e.artist, e.album, e.shuffle)
    data = [e.model_dump() for e in body]
    QUICKPLAY_FILE.write_text(json.dumps(data, indent=2))
    return {"quickplay": data}


@router.put("/quickplay/{index}")
def update_quickplay_entry(index: int, body: QuickplayEntry):
    label = "shuffle all" if body.shuffle else (f"{body.artist}" + (f" / {body.album}" if body.album else ""))
    logger.info(f"Updating quickplay entry {index}: {label}")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    with mpd_connection() as mpd:
        _validate_entry(mpd, body.artist, body.album, body.shuffle)
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
        with mpd_connection() as mpd:
            mpd.clear()
            mpd.add("Subsonic/Albums")
            mpd.shuffle()
            mpd.play()
        return {"status": "playing", "shuffle": True}
    logger.info(f"Quickplay {index}: {artist}" + (f" / {album}" if album else " (all albums)"))
    path = f"Subsonic/Artists/{artist}/{album}" if album else f"Subsonic/Artists/{artist}"
    with mpd_connection() as mpd:
        _validate_entry(mpd, artist, album)
        mpd.clear()
        mpd.add(path)
        mpd.play()
    result = {"status": "playing", "artist": artist}
    if album:
        result["album"] = album
    return result
