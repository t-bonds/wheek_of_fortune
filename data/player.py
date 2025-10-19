from dataclasses import dataclass


@dataclass
class Player:
    name: str
    round_score: float = 0.0
    total_score: float = 0.0
    has_spun = False

    def set_bankrupt(self) -> None:
        self.round_score = 0.0

    def set_money(self, amount) -> None:
        self.round_score = amount

    def add_money(self, amount) -> None:
        self.round_score += amount

    def add_total_money(self) -> None:
        self.total_score += self.round_score

    def set_total_money(self, amount) -> None:
        self.total_score = amount


class Players:
    def __init__(self, players: list[str]) -> None:
        self.players: list[Player] = [Player(name=player) for player in players]

    def get_players(self) -> list[Player]:
        return self.players

    def get_player(self, name) -> Player:
        return next([player for player in self.players if player.name == name])
