from __future__ import annotations

import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gameplay.radio import RADIO_STATIONS, RadioPlayer


def main() -> int:
    populated = [station for station in RADIO_STATIONS if station is not None]
    assert len(RADIO_STATIONS) == 10
    assert [station.name for station in populated] == [
        "OOC Radio", "Hive365", "Radio Free Zion",
    ]
    assert all(station.stream_url.startswith(("http://", "https://")) for station in populated)

    player = RadioPlayer()
    assert player.select(2) and player.selected_index == 2
    assert not player.select(9) and player.selected_index == 2
    assert player.toggle_muted() is True
    player.stop()

    client_source = (ROOT / "client.py").read_text(encoding="utf-8")
    audio_source = (ROOT / "gameplay" / "audio.py").read_text(encoding="utf-8")
    ast.parse(client_source, filename="client.py")
    ast.parse(audio_source, filename="gameplay/audio.py")
    for token in (
        "_draw_audio_icons", "_radio_slot_layout", "CAR RADIO",
        "self.radio.toggle_muted()", "self.audio.toggle_muted()",
        "_draw_main_audio_icons", "handle_main_audio_click",
        "desired_station = None", "self.radio.update(None)",
    ):
        assert token in client_source, token
    assert "self.game_audio_muted or not self.enabled" in audio_source
    assert "for sound in self.sounds.values()" in audio_source

    radio_source = (ROOT / "gameplay" / "radio.py").read_text(encoding="utf-8")
    for token in ("imageio_ffmpeg.get_ffmpeg_exe()", "pcm_s16le", "self._channel.queue(sound)"):
        assert token in radio_source, token
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "imageio-ffmpeg" in requirements and "python-vlc" not in requirements

    print("OPEN NIGHT v1.7 RADIO / AUDIO AUDIT: PASS")
    print("  3 live stations + 10 car slots + vehicle-only playback + visible independent mute controls")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
