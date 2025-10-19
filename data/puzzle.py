from dataclasses import dataclass
import json
import sys
from pathlib import Path


@dataclass
class Puzzle:
    category: str
    phrase: str
    type: str
    prize_value: float


class Puzzles:
    def __init__(self) -> None:
        self.PUZZLES_FILE: Path = Path(__file__).parent / "puzzles.json"
        self.puzzles = self.load_puzzles()

    def ensure_puzzles_file(self) -> None:
        if not self.PUZZLES_FILE.exists():
            print("NO PUZZLES FILE")
            sys.exit(1)

    def load_puzzles(self) -> list:
        self.ensure_puzzles_file()
        raw = self.PUZZLES_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        puzzles: list = []
        for item in data:
            if isinstance(item, dict):
                puzzles.append(
                    Puzzle(
                        category=item["category"],
                        phrase=item["phrase"],
                        type=item.get("type", "MAIN"),
                        prize_value=item.get("prize_value", 0.0),
                    )
                )
        return puzzles

    def get_puzzles(self) -> list:
        return self.puzzles

    def get_puzzle(self, idx) -> Puzzle:
        return self.puzzles[idx]

    def get_prize_value(self, idx) -> float:
        p = self.get_puzzle(idx)
        return p.prize_value
