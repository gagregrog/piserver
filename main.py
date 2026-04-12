import logging
import sys
from contextlib import contextmanager
from fastapi import FastAPI
from mpd import MPDClient

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
        albums = mpd.list("album")
    return {"albums": albums}

@app.post("/album/{name}")
def play_album(name: str):
    logger.info(f"Playing album: {name}")
    with mpd_connection() as mpd:
        mpd.clear()
        mpd.searchadd("album", name)
        mpd.play()
    return {"status": "playing", "album": name}
