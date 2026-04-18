import json
import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from mpd import MPDClient, CommandError
from pydantic import BaseModel

QUICKPLAY_FILE = Path(__file__).parent / "quickplay.json"

# Logging setup
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    file_handler = logging.FileHandler("/home/pi/piserver/piserver.log")
    file_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)
    logger.addHandler(file_handler)

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI()

@contextmanager
def mpd_connection():
    client = MPDClient()
    client.connect("localhost", 6600)
    try:
        yield client
    finally:
        client.disconnect()

@app.post("/play")
def play():
    logger.info("Play command received")
    with mpd_connection() as mpd:
        mpd.play()
    return {"status": "playing"}

@app.post("/stop")
def stop():
    logger.info("Stop command received")
    with mpd_connection() as mpd:
        mpd.stop()
    return {"status": "stopped"}

@app.post("/playlist/{name}")
def load_playlist(name: str):
    logger.info(f"Loading playlist: {name}")
    with mpd_connection() as mpd:
        mpd.clear()
        mpd.load(name)
        mpd.play()
    return {"status": "loaded", "playlist": name}

@app.get("/albums")
def list_albums():
    logger.info("Listing albums")
    with mpd_connection() as mpd:
        entries = mpd.lsinfo("Subsonic/Albums")
    albums = [e["directory"].split("/")[-1] for e in entries if "directory" in e]
    return {"albums": albums}

@app.get("/artists")
def list_artists():
    logger.info("Listing artists")
    with mpd_connection() as mpd:
        entries = mpd.lsinfo("Subsonic/Artists")
    artists = [e["directory"].split("/")[-1] for e in entries if "directory" in e]
    return {"artists": artists}

@app.get("/artist/{name}/albums")
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

@app.post("/artist/{artist}/album/{album}")
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

class QuickplayEntry(BaseModel):
    artist: str
    album: str

def _validate_album(mpd, artist: str, album: str):
    path = f"Subsonic/Artists/{artist}/{album}"
    try:
        entries = mpd.lsinfo(path)
    except CommandError:
        raise HTTPException(status_code=404, detail=f"Album not found: {artist} / {album}")
    if not entries:
        raise HTTPException(status_code=404, detail=f"Album is empty: {artist} / {album}")

@app.get("/quickplay")
def get_quickplay():
    logger.info("Getting quickplay list")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    return {"quickplay": entries}

@app.get("/quickplay/{index}")
def get_quickplay_entry(index: int):
    logger.info(f"Getting quickplay entry {index}")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    return {"index": index, **entries[index]}

@app.put("/quickplay")
def replace_quickplay(body: list[QuickplayEntry]):
    logger.info(f"Replacing quickplay list ({len(body)} entries)")
    with mpd_connection() as mpd:
        for e in body:
            _validate_album(mpd, e.artist, e.album)
    data = [e.model_dump() for e in body]
    QUICKPLAY_FILE.write_text(json.dumps(data, indent=2))
    return {"quickplay": data}

@app.put("/quickplay/{index}")
def update_quickplay_entry(index: int, body: QuickplayEntry):
    logger.info(f"Updating quickplay entry {index}: {body.artist} / {body.album}")
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    with mpd_connection() as mpd:
        _validate_album(mpd, body.artist, body.album)
    entries[index] = body.model_dump()
    QUICKPLAY_FILE.write_text(json.dumps(entries, indent=2))
    return {"index": index, **entries[index]}

@app.post("/quickplay/{index}")
def quickplay(index: int):
    entries = json.loads(QUICKPLAY_FILE.read_text())
    if index < 0 or index >= len(entries):
        raise HTTPException(status_code=404, detail=f"No quickplay entry at index {index}")
    entry = entries[index]
    artist = entry["artist"]
    album = entry["album"]
    logger.info(f"Quickplay {index}: {artist} / {album}")
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
