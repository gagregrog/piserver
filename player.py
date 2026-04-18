from contextlib import contextmanager

from mpd import CommandError, MPDClient

ALBUMS_PATH = "Subsonic/Albums"
ARTISTS_PATH = "Subsonic/Artists"


class NotFoundError(Exception):
    pass


@contextmanager
def _connection():
    client = MPDClient()
    client.connect("localhost", 6600)
    try:
        yield client
    finally:
        client.disconnect()


def toggle_play() -> str:
    with _connection() as mpd:
        state = mpd.status()["state"]
        if state == "play":
            mpd.pause(1)
            return "paused"
        elif state == "pause":
            mpd.pause(0)
            return "playing"
        else:
            mpd.play()
            return "playing"


def shuffle_all() -> None:
    with _connection() as mpd:
        mpd.clear()
        mpd.add(ALBUMS_PATH)
        mpd.shuffle()
        mpd.play()


def stop() -> None:
    with _connection() as mpd:
        mpd.stop()


def next_track() -> None:
    with _connection() as mpd:
        mpd.next()


def previous_track() -> None:
    with _connection() as mpd:
        mpd.previous()


def restart_track() -> None:
    with _connection() as mpd:
        mpd.seekcur(0)


def current_track() -> dict:
    with _connection() as mpd:
        status = mpd.status()
        song = mpd.currentsong()
    return {"status": status["state"], "track": song}


def get_queue() -> list:
    with _connection() as mpd:
        return mpd.playlistinfo()


def load_playlist(name: str) -> None:
    with _connection() as mpd:
        mpd.clear()
        mpd.load(name)
        mpd.play()


def list_albums() -> list[str]:
    with _connection() as mpd:
        entries = mpd.lsinfo(ALBUMS_PATH)
    return [e["directory"].split("/")[-1] for e in entries if "directory" in e]


def list_artists() -> list[str]:
    with _connection() as mpd:
        entries = mpd.lsinfo(ARTISTS_PATH)
    return [e["directory"].split("/")[-1] for e in entries if "directory" in e]


def list_artist_albums(artist: str) -> list[str]:
    path = f"{ARTISTS_PATH}/{artist}"
    with _connection() as mpd:
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise NotFoundError(f"Artist not found: {artist}")
    albums = [e["directory"].split("/")[-1] for e in entries if "directory" in e]
    if not albums:
        raise NotFoundError(f"No albums found for artist: {artist}")
    return albums


def play_artist(artist: str) -> None:
    path = f"{ARTISTS_PATH}/{artist}"
    with _connection() as mpd:
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise NotFoundError(f"Artist not found: {artist}")
        if not [e for e in entries if "directory" in e]:
            raise NotFoundError(f"No albums found for artist: {artist}")
        mpd.clear()
        mpd.add(path)
        mpd.play()


def play_album(artist: str, album: str) -> None:
    path = f"{ARTISTS_PATH}/{artist}/{album}"
    with _connection() as mpd:
        try:
            entries = mpd.lsinfo(path)
        except CommandError:
            raise NotFoundError(f"Album not found: {artist} / {album}")
        if not entries:
            raise NotFoundError(f"Album is empty: {artist} / {album}")
        mpd.clear()
        mpd.add(path)
        mpd.play()


def validate_entry(artist: str | None, album: str | None, shuffle: bool = False) -> None:
    if shuffle:
        return
    if album is not None:
        path = f"{ARTISTS_PATH}/{artist}/{album}"
        with _connection() as mpd:
            try:
                entries = mpd.lsinfo(path)
            except CommandError:
                raise NotFoundError(f"Album not found: {artist} / {album}")
        if not entries:
            raise NotFoundError(f"Album is empty: {artist} / {album}")
    else:
        path = f"{ARTISTS_PATH}/{artist}"
        with _connection() as mpd:
            try:
                entries = mpd.lsinfo(path)
            except CommandError:
                raise NotFoundError(f"Artist not found: {artist}")
        if not [e for e in entries if "directory" in e]:
            raise NotFoundError(f"No albums found for artist: {artist}")
