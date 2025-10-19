from pathlib import Path
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QSoundEffect
from PySide6.QtCore import QUrl

SOUNDS_DIR: Path = Path(__file__).parent.parent.resolve() / "sounds"


class SoundsManager:
    def __init__(self) -> None:
        self.files: dict[str, Path] = self.link_sounds()
        self.effects: dict = {}
        self._audio_outputs: dict[str, QAudioOutput] = {}
        for name, p in self.files.items():
            se = QMediaPlayer() if p.suffix == ".mp3" else QSoundEffect()

            se.setSource(QUrl.fromLocalFile(str(p.resolve())))
            if p.suffix == ".mp3":
                ao = QAudioOutput()
                ao.setVolume(0.9)
                se.setAudioOutput(ao)
                self._audio_outputs[name] = ao

            self.effects[name] = se

    def link_sounds(self) -> dict[str, Path]:
        if not SOUNDS_DIR.exists():
            SOUNDS_DIR.mkdir(parents=True)
        files = {
            "LETTER_REVEAL": SOUNDS_DIR / "LETTER_REVEAL.mp3",
            "INCORRECT": SOUNDS_DIR / "INCORRECT.mp3",
            "BANKRUPT": SOUNDS_DIR / "BANKRUPT.mp3",
            "BONUS_CHOOSE": SOUNDS_DIR / "BONUS_CHOOSE.mp3",
            "COUNTDOWN": SOUNDS_DIR / "COUNTDOWN.mp3",
            "PUZZLE_REVEAL": SOUNDS_DIR / "PUZZLE_REVEAL.mp3",
            "PUZZLE_SOLVE": SOUNDS_DIR / "PUZZLE_SOLVE.mp3",
            "THEME": SOUNDS_DIR / "THEME.mp3",
            "TOSS-UP_SOLVE": SOUNDS_DIR / "TOSS-UP_SOLVE.mp3",
            "TOSS-UP": SOUNDS_DIR / "TOSS-UP.mp3",
            "BEEP": SOUNDS_DIR / "BEEP.wav",
        }
        return files

    def play(self, name: str, loop: bool = False) -> None:
        if name not in self.effects:
            return
        se = self.effects[name]
        try:
            if loop:
                se.setLoops(QMediaPlayer.Infinite)
            se.stop()
            se.play()
        except Exception:
            pass

    def stop(self, name: str) -> None:
        if name not in self.effects:
            return
        se = self.effects[name]
        try:
            se.stop()
        except Exception:
            pass
