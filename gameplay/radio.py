from __future__ import annotations

"""Fail-soft live radio playback for desktop builds.

The game remains playable without VLC/LibVLC; in that case the radio UI reports
that the optional playback backend is unavailable while all ordinary SFX keep
working through pygame.mixer.
"""

from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class RadioStation:
    name: str
    genre: str
    stream_url: str


RADIO_STATIONS: tuple[RadioStation | None, ...] = (
    RadioStation("OOC Radio", "Variety / live DJs", "https://radio.oocradio.com/"),
    RadioStation("Hive365", "Pop / dance / variety", "http://stream.hive365.co.uk:8088/live"),
    RadioStation("Radio Free Zion", "Alternative / community", "https://stream.radiofreezion.net:8061/listen.mp3"),
    None,
    None,
    None,
    None,
    None,
    None,
    None,
)


class RadioPlayer:
    def __init__(self) -> None:
        self.music_muted = False
        self.selected_index = 0
        self.playing_index: int | None = None
        self._player = None
        self._vlc = None
        self.error = ""
        if sys.platform == "emscripten":
            self.error = "Live radio is currently available in the desktop build."
            return
        try:
            import vlc  # type: ignore

            self._vlc = vlc
        except (ImportError, OSError) as exc:
            self.error = f"Live radio needs VLC: {exc}"

    @property
    def available(self) -> bool:
        return self._vlc is not None

    @property
    def selected(self) -> RadioStation | None:
        return RADIO_STATIONS[self.selected_index]

    def select(self, index: int) -> bool:
        if not 0 <= index < len(RADIO_STATIONS) or RADIO_STATIONS[index] is None:
            return False
        self.selected_index = index
        if self.playing_index != index:
            self.stop()
        return True

    def set_muted(self, muted: bool) -> None:
        self.music_muted = bool(muted)
        if self._player is not None:
            try:
                self._player.audio_set_mute(self.music_muted)
            except Exception:
                pass

    def toggle_muted(self) -> bool:
        self.set_muted(not self.music_muted)
        return self.music_muted

    def update(self, desired_index: int | None, volume: int = 62) -> None:
        if desired_index is None or self.music_muted:
            if self._player is not None:
                try:
                    self._player.audio_set_mute(True)
                except Exception:
                    pass
            return
        if not self.available or not 0 <= desired_index < len(RADIO_STATIONS):
            return
        station = RADIO_STATIONS[desired_index]
        if station is None:
            return
        if self.playing_index != desired_index or self._player is None:
            self.stop()
            try:
                self._player = self._vlc.MediaPlayer(station.stream_url)
                self._player.audio_set_volume(max(0, min(100, int(volume))))
                self._player.play()
                self.playing_index = desired_index
                self.error = ""
            except Exception as exc:
                self.error = f"Could not start {station.name}: {exc}"
                self._player = None
                self.playing_index = None
        else:
            try:
                self._player.audio_set_mute(False)
                self._player.audio_set_volume(max(0, min(100, int(volume))))
            except Exception:
                pass

    def stop(self) -> None:
        if self._player is not None:
            try:
                self._player.stop()
            except Exception:
                pass
        self._player = None
        self.playing_index = None

