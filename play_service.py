import ir_blaster
import player


def toggle_play() -> str:
    # Check state first so IR only fires on a transition to playing.
    if player.current_track()["status"] != "play":
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
