from __future__ import annotations

"""Fail-soft live radio decoded by a bundled FFmpeg binary on desktop."""

from dataclasses import dataclass
import subprocess
import sys
import threading

import pygame


@dataclass(frozen=True)
class RadioStation:
    name: str
    genre: str
    stream_url: str


RADIO_STATIONS: tuple[RadioStation | None, ...] = (
    RadioStation("OOC Radio", "Variety / live DJs", "https://radio.oocradio.com/"),
    RadioStation("Hive365", "Pop / dance / variety", "http://stream.hive365.co.uk:8088/live"),
    RadioStation("Radio Free Zion", "Alternative / community", "https://stream.radiofreezion.net:8061/listen.mp3"),
    None, None, None, None, None, None, None,
)


class RadioPlayer:
    SAMPLE_RATE = 44100
    CHANNEL_INDEX = 0
    CHUNK_BYTES = SAMPLE_RATE * 2 * 2 // 2

    def __init__(self) -> None:
        self.music_muted = False
        self.selected_index = 0
        self.playing_index: int | None = None
        self.error = ""
        self._ffmpeg_exe = ""
        self._process: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._generation = 0
        self._channel: pygame.mixer.Channel | None = None
        if sys.platform == "emscripten":
            self.error = "Live radio is currently available in the desktop build."
            return
        try:
            import imageio_ffmpeg

            self._ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        except (ImportError, OSError) as exc:
            self.error = f"Live radio decoder unavailable: {exc}"

    @property
    def available(self) -> bool:
        return bool(self._ffmpeg_exe)

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
        if self._channel is not None:
            self._channel.set_volume(0.0 if self.music_muted else 0.62)

    def toggle_muted(self) -> bool:
        self.set_muted(not self.music_muted)
        return self.music_muted

    def update(self, desired_index: int | None, volume: int = 62) -> None:
        # The radio belongs to a vehicle, never to the surrounding map region.
        # Leaving a car must also stop an already-buffered stream; merely skipping
        # the next update leaves the mixer channel and FFmpeg worker running.
        if desired_index is None:
            if self.playing_index is not None or self._thread is not None or self._channel is not None:
                self.stop()
            return
        if self.music_muted or not self.available:
            return
        if not 0 <= desired_index < len(RADIO_STATIONS) or RADIO_STATIONS[desired_index] is None:
            return
        if self.playing_index != desired_index or self._thread is None or not self._thread.is_alive():
            self._start(desired_index, volume)
        elif self._channel is not None:
            self._channel.set_volume(max(0.0, min(1.0, volume / 100.0)))

    def _start(self, index: int, volume: int) -> None:
        self.stop()
        if not pygame.mixer.get_init():
            self.error = "Audio mixer is not initialized."
            return
        pygame.mixer.set_num_channels(max(16, pygame.mixer.get_num_channels()))
        pygame.mixer.set_reserved(1)
        self._channel = pygame.mixer.Channel(self.CHANNEL_INDEX)
        self._channel.set_volume(max(0.0, min(1.0, volume / 100.0)))
        self._stop_event.clear()
        self._generation += 1
        generation = self._generation
        self.playing_index = index
        self.error = "Connecting..."
        self._thread = threading.Thread(target=self._decode, args=(index, generation), daemon=True)
        self._thread.start()

    def _decode(self, index: int, generation: int) -> None:
        station = RADIO_STATIONS[index]
        if station is None:
            return
        command = [
            self._ffmpeg_exe, "-nostdin", "-loglevel", "error",
            "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5",
            "-i", station.stream_url, "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
            "-ac", "2", "-ar", str(self.SAMPLE_RATE), "pipe:1",
        ]
        first = True
        process = None
        try:
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self._process = process
            while not self._stop_event.is_set() and generation == self._generation:
                data = process.stdout.read(self.CHUNK_BYTES) if process.stdout else b""
                if len(data) < 4096:
                    break
                sound = pygame.mixer.Sound(buffer=data)
                while (self._channel is not None and self._channel.get_queue() is not None
                       and not self._stop_event.wait(0.01)):
                    pass
                if self._stop_event.is_set() or generation != self._generation:
                    break
                if self._channel is not None:
                    if first or not self._channel.get_busy():
                        self._channel.play(sound)
                        first = False
                        self.error = ""
                    else:
                        self._channel.queue(sound)
            if first and generation == self._generation:
                self.error = f"{station.name} stream did not return audio."
        except (OSError, pygame.error) as exc:
            if generation == self._generation:
                self.error = f"Could not play {station.name}: {exc}"
        finally:
            if process is not None and process.poll() is None:
                process.terminate()

    def stop(self) -> None:
        self._generation += 1
        self._stop_event.set()
        if self._channel is not None:
            self._channel.stop()
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.4)
        self._process = None
        self._thread = None
        self._channel = None
        self.playing_index = None
        self._stop_event.clear()
