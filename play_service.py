import config
import ir_blaster
import player


def toggle_play() -> str:
    state = player.current_track()["status"]
    if state == "play":
        # Playing → pause. No IR needed.
        return player.toggle_play()
    if state == "pause":
        # Paused → resume the current queue.
        ir_blaster.select_stereo_input()
        return player.toggle_play()
    # Stopped / nothing queued → start the first quickplay entry (if any),
    # otherwise fall back to a plain play.
    entries = config.load().get("quickplay", [])
    if entries:
        play_quickplay(0)
        return "playing"
    ir_blaster.select_stereo_input()
    return player.toggle_play()


def shuffle_all() -> None:
    ir_blaster.select_stereo_input()
    player.shuffle_all()


def load_playlist(name: str) -> None:
    ir_blaster.select_stereo_input()
    player.load_playlist(name)


def play_artist(artist: str) -> None:
    ir_blaster.select_stereo_input()
    player.play_artist(artist)


def play_album(artist: str, album: str) -> None:
    ir_blaster.select_stereo_input()
    player.play_album(artist, album)


def play_quickplay(index: int) -> dict:
    """Play the quickplay entry at the given index. Raises IndexError if out of
    range, or player.NotFoundError if the stored artist/album no longer exists."""
    entries = config.load().get("quickplay", [])
    if index < 0 or index >= len(entries):
        raise IndexError(f"No quickplay entry at index {index}")
    entry = entries[index]
    if entry.get("shuffle", False):
        shuffle_all()
        return {"status": "playing", "shuffle": True}
    artist = entry.get("artist")
    album = entry.get("album")
    if album:
        play_album(artist, album)
    else:
        play_artist(artist)
    result = {"status": "playing", "artist": artist}
    if album:
        result["album"] = album
    return result
