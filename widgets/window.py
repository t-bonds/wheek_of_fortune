from multiprocessing import Lock
import sys
import random
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.append(str(Path(__file__).parent.parent.resolve()))

from widgets import WheelWidget, BoardWidget
from data import Puzzles, Players
from utils import fmt_money

from data import VOWEL_COST, Puzzle, Player


class GameWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Wheel of Fortune")
        self.resize(1200, 720)

        # Sound manager
        from widgets import SoundsManager

        self.sounds: SoundsManager = SoundsManager()

        # Puzzles & game state
        self.puzzle_class: Puzzles = Puzzles()
        self.puzzles: list[Puzzle] = self.puzzle_class.get_puzzles()
        self.current_puzzle_index: int = -1
        self.current_player_index: int = -1
        self.round_number: int = -1
        self.main_rounds_total: int = len([x for x in self.puzzles if x.type == "MAIN"])
        self.tossups: int = len([x for x in self.puzzles if x.type == "TOSS-UP"])
        self.current_phase: str = "SETUP"

        # last spin wedge monetary value for use by letter selection
        self.last_spin_value: float | None = None

        # toss-up reveal timer + paused flag (interval settable)
        self._tossup_timer: QtCore.QTimer = QtCore.QTimer()
        self._tossup_timer.setInterval(1500)  # default 1500 ms
        self._tossup_timer.timeout.connect(self.tossup_reveal_step)
        self.tossup_paused: bool = False

        self._build_ui()
        self.show_setup_dialog()

    def _build_ui(self) -> None:
        central: QtWidgets.QWidget = QtWidgets.QWidget()
        h: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        central.setLayout(h)

        # Left: wheel and controls
        self.wheel: WheelWidget = WheelWidget(self)
        self.wheel.spin_finished.connect(self.on_wheel_result)
        left_v: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        left_v.addWidget(self.wheel)
        self.spin_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Spin")
        self.spin_btn.clicked.connect(self.do_spin)
        left_v.addWidget(self.spin_btn)
        left_w: QtWidgets.QWidget = QtWidgets.QWidget()
        left_w.setLayout(left_v)
        h.addWidget(left_w, 2)

        # Center: board and letter-grid inputs
        center_v: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        self.board: BoardWidget = BoardWidget(self)
        center_v.addWidget(self.board)

        # Letter grid (A-Z) for host selection
        letters_group: QtWidgets.QGroupBox = QtWidgets.QGroupBox("Letters")
        grid: QtWidgets.QGridLayout = QtWidgets.QGridLayout()
        self.letter_buttons: dict[str, QtWidgets.QPushButton] = {}
        all_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        cols = 9
        for idx, ch in enumerate(all_letters):
            btn: QtWidgets.QPushButton = QtWidgets.QPushButton(ch)
            btn.setFixedSize(48, 36)
            btn.setProperty("letter", ch)
            btn.clicked.connect(
                lambda checked, letter=ch: self.on_letter_selected(letter)
            )
            row = idx // cols
            col = idx % cols
            grid.addWidget(btn, row, col)
            self.letter_buttons[ch] = btn
        letters_group.setLayout(grid)
        center_v.addWidget(letters_group)

        # Host solve adjudication buttons (no textual entry)
        solve_h: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        self.solve_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Solve")
        self.solve_btn.clicked.connect(self.solve_button_action)
        solve_h.addWidget(self.solve_btn)
        center_v.addLayout(solve_h)

        # Admin puzzle controls
        admin_h: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        self.next_puzzle_btn: QtWidgets.QPushButton = QtWidgets.QPushButton(
            "Next Puzzle"
        )
        self.next_puzzle_btn.clicked.connect(self._next_phase)
        admin_h.addWidget(self.next_puzzle_btn)
        center_v.addLayout(admin_h)

        center_w = QtWidgets.QWidget()
        center_w.setLayout(center_v)
        h.addWidget(center_w, 3)

        # Right: players UI
        right_v: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        players_title: QtWidgets.QLabel = QtWidgets.QLabel("Players")
        players_title.setFont(QtGui.QFont("", 14, QtGui.QFont.Bold))
        right_v.addWidget(players_title)
        self.players_list_widget: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        right_v.addLayout(self.players_list_widget)

        # Admin override controls (select player, set money, undo)
        override_group: QtWidgets.QGroupBox = QtWidgets.QGroupBox(
            "Override Player Score"
        )
        ov_layout: QtWidgets.QFormLayout = QtWidgets.QFormLayout()
        self.override_player_cb: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.override_round_spin: QtWidgets.QDoubleSpinBox = QtWidgets.QDoubleSpinBox()
        self.override_round_spin.setPrefix("$")
        self.override_round_spin.setMaximum(1000000)
        self.override_total_spin: QtWidgets.QDoubleSpinBox = QtWidgets.QDoubleSpinBox()
        self.override_total_spin.setPrefix("$")
        self.override_total_spin.setMaximum(1000000)
        apply_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Apply Override")
        apply_btn.clicked.connect(self.override_score)
        ov_layout.addRow("Player:", self.override_player_cb)
        ov_layout.addRow("Round Score:", self.override_round_spin)
        ov_layout.addRow("Total Score:", self.override_total_spin)
        ov_layout.addRow(apply_btn)
        override_group.setLayout(ov_layout)
        right_v.addWidget(override_group)

        # Status label
        self.status_label: QtWidgets.QLabel = QtWidgets.QLabel("Status: Setup")
        right_v.addWidget(self.status_label)

        right_v.addStretch()
        right_w: QtWidgets.QWidget = QtWidgets.QWidget()
        right_w.setLayout(right_v)
        h.addWidget(right_w, 2)

        self.setCentralWidget(central)

    def show_setup_dialog(self) -> None:
        self.sounds.play("THEME", loop=True)
        dlg: QtWidgets.QDialog = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Player Setup")
        layout: QtWidgets.QFormLayout = QtWidgets.QFormLayout(dlg)

        num_players_spin: QtWidgets.QSpinBox = QtWidgets.QSpinBox()
        num_players_spin.setMinimum(1)
        num_players_spin.setValue(3)
        layout.addRow("Number of Players:", num_players_spin)

        rounds_spin: QtWidgets.QLabel = QtWidgets.QLabel()
        rounds_spin.setText(str(self.main_rounds_total))
        layout.addRow("Main Rounds:", rounds_spin)

        tossups_spin: QtWidgets.QLabel = QtWidgets.QLabel()
        tossups_spin.setText(str(self.tossups))
        layout.addRow("Toss-Ups:", tossups_spin)

        final_spin: QtWidgets.QLabel = QtWidgets.QLabel()
        final_spin.setText(
            "True"
            if any([True if x.type == "FINAL SPIN" else False for x in self.puzzles])
            else "False"
        )
        layout.addRow("Final Spin:", final_spin)

        bonus_round: QtWidgets.QLabel = QtWidgets.QLabel()
        bonus_round.setText(
            "True"
            if any([True if x.type == "BONUS ROUND" else False for x in self.puzzles])
            else "False"
        )
        layout.addRow("Bonus Round:", bonus_round)

        # Create a dedicated container (widget + vbox layout) to hold dynamic name fields.
        name_container: QtWidgets.QWidget = QtWidgets.QWidget()
        name_layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_container.setLayout(name_layout)
        layout.addRow(name_container)

        name_edits: list[QtWidgets.QLineEdit] = []

        def on_num_changed(v) -> None:
            target: int = num_players_spin.value()
            # add fields
            while len(name_edits) < target:
                le: QtWidgets.QLineEdit = QtWidgets.QLineEdit()
                le.setPlaceholderText(f"Player {len(name_edits) + 1}")
                name_edits.append(le)
                name_layout.addWidget(
                    QtWidgets.QLabel(f"Player {len(name_edits)} name:")
                )
                name_layout.addWidget(le)
            # remove fields
            while len(name_edits) > target:
                le: QtWidgets.QLineEdit = name_edits.pop()
                # remove its label and the line edit from name_layout
                # last two widgets correspond to that entry (label + edit)
                item: QtWidgets.QLayoutItem = name_layout.takeAt(
                    name_layout.count() - 1
                )
                if item and item.widget():
                    item.widget().deleteLater()

        num_players_spin.valueChanged.connect(on_num_changed)
        on_num_changed(None)  # populate initial fields

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        layout.addRow(buttons)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        if dlg.exec() == QtWidgets.QDialog.Accepted:
            players = []
            for i, le in enumerate(name_edits):
                name = le.text().strip() or f"Player {i + 1}"
                players.append(name)
            self.players_class: Players = Players(players)
            self.players: list[Player] = self.players_class.get_players()
            self.main_rounds_total = int(rounds_spin.text())
            self.tossups = int(tossups_spin.text())
            self._rebuild_players_panel()
            self.status_label.setText("Welcome to Wheel of Fortune!")
            self.start_game()
        else:
            sys.exit(0)

    def _rebuild_players_panel(self) -> None:
        # clear layout
        while self.players_list_widget.count():
            item: QtWidgets.QLayoutItem = self.players_list_widget.takeAt(0)
            w: QtWidgets.QWidget = item.widget()
            if w:
                w.setParent(None)
        # recreate player rows
        self.override_player_cb.clear()
        for idx, p in enumerate(self.players):
            w: QtWidgets.QWidget = QtWidgets.QWidget()
            h: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
            lbl: QtWidgets.QLabel = QtWidgets.QLabel(p.name)
            lbl.setMinimumWidth(120)
            score_lbl: QtWidgets.QLabel = QtWidgets.QLabel(
                f"Round: {fmt_money(amount=p.round_score)} / Total: {fmt_money(amount=p.total_score)}"
            )
            score_lbl.setObjectName(f"score_{idx}")
            # Host buzzer button (big) to indicate host wants to select that player
            set_turn_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("SET TURN")
            set_turn_btn.setProperty("player_index", idx)
            set_turn_btn.setMinimumHeight(36)
            set_turn_btn.clicked.connect(lambda checked, i=idx: self.host_set_turn(i))
            h.addWidget(lbl)
            h.addWidget(score_lbl)
            h.addWidget(set_turn_btn)
            w.setLayout(h)
            self.players_list_widget.addWidget(w)
            self.override_player_cb.addItem(p.name)

        self._update_player_scores_ui()

    def _update_player_scores_ui(self):
        for i in range(self.players_list_widget.count()):
            w: QtWidgets.QWidget = self.players_list_widget.itemAt(i).widget()
            if w:
                labels: list[QtWidgets.QLabel] = w.findChildren(QtWidgets.QLabel)
                if len(labels) >= 2:
                    score_lbl: QtWidgets.QLabel = labels[1]
                    p: Player = self.players[i]
                    score_lbl.setText(
                        f"Round: {fmt_money(p.round_score)} / Total: {fmt_money(p.total_score)}"
                    )
        # update override combobox values
        self.override_player_cb.clear()
        for p in self.players:
            self.override_player_cb.addItem(p.name)

    def solve_button_action(self) -> None:
        if self.current_phase == "TOSS-UP":
            self.pause_tossup()
        else:
            self.solve_dlg: QtWidgets.QDialog = QtWidgets.QDialog(self)
            layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
            self.solve_dlg.setWindowTitle("Solve?")
            correct_tossup_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Correct")
            incorrect_tossup_btn: QtWidgets.QPushButton = QtWidgets.QPushButton(
                "Incorrect"
            )
            layout.addWidget(correct_tossup_btn)
            layout.addWidget(incorrect_tossup_btn)
            self.solve_dlg.setLayout(layout)
            correct_tossup_btn.clicked.connect(self.solve_and_reveal)
            incorrect_tossup_btn.clicked.connect(self.incorrect_solve)
            self.solve_dlg.setModal(True)
            if self.current_phase == "FINAL SPIN":
                self.sounds.play("LETTER_REVEAL")
            self.solve_dlg.show()

    def start_game(self) -> None:
        self.sounds.stop(name="THEME")
        self.status_label.setText("")
        self._next_phase()

    def _next_phase(self) -> None:
        self.board.load_puzzle(puzzle=self._pop_next_puzzle())
        self.next_puzzle_btn.setEnabled(False)
        self.solve_btn.setEnabled(True)

        if self.current_phase == "TOSS-UP":
            self.current_player_index = -1
            self.go_to_tossup()
        else:
            self.round_number += 1
            self.current_player_index = self.round_number % len(self.players)
            if self.current_phase == "MAIN":
                self._start_main_round()
            elif self.current_phase == "FINAL SPIN":
                self._start_final_spin()
            elif self.current_phase == "BONUS ROUND":
                top: Player = max(self.players, key=lambda x: x.total_score)
                self.current_player_index = self.players.index(top)
                self._start_bonus_round()

    def go_to_tossup(self) -> None:
        self.tossup_dlg: QtWidgets.QDialog = QtWidgets.QDialog(self)
        layout: QtWidgets.QHBoxLayout = QtWidgets.QHBoxLayout()
        self.tossup_dlg.setWindowTitle("Start Toss-Up?")
        self.start_tossup_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Start")
        layout.addWidget(self.start_tossup_btn)
        self.tossup_dlg.setLayout(layout)
        self.start_tossup_btn.clicked.connect(self._start_tossup)
        self.tossup_dlg.setModal(True)
        self.tossup_dlg.show()

    def _start_tossup(self) -> None:
        if self.tossup_dlg.isVisible():
            self.tossup_dlg.accept()
        self.solve_btn.setEnabled(True)
        self.spin_btn.setEnabled(False)
        [x.setEnabled(False) for x in self.letter_buttons.values()]
        self.sounds.play("TOSS-UP", loop=True)
        reveal_count: int = max(1, int(len(self.board.correct_letters) * 0.2))
        choices: list[str] = [
            c for c in self.board.correct_letters if c not in set("AEIOU")
        ]
        random.shuffle(choices)
        for c in choices[:reveal_count]:
            self.board.revealed.add(c)
        self.board.update_display()
        self.tossup_paused = False
        if self._tossup_timer.isActive():
            self._tossup_timer.stop()
        self._tossup_timer.start()

    def _pop_next_puzzle(self) -> Puzzle:
        if not self.puzzles:
            raise RuntimeError("No puzzles")
        self.current_puzzle_index = (self.current_puzzle_index + 1) % len(self.puzzles)
        p: Puzzle = self.puzzles[self.current_puzzle_index]
        self.current_phase = p.type
        return p

    def _start_main_round(self) -> None:
        self.spin_btn.setEnabled(True)
        self.solve_btn.setEnabled(True)
        self.status_label.setText(
            f"Turn: {self.players[self.current_player_index].name}"
        )
        for p in self.players:
            p.round_score = 0.0
        self._update_player_scores_ui()

    def _start_final_spin(self) -> None:
        self.spin_btn.setEnabled(True)
        self.solve_btn.setEnabled(False)
        self.sounds.play("FINAL_SPIN")

    def _start_bonus_round(self) -> None:
        self.sounds.play("BONUS_CHOOSE")
        for ch in "RSTLNE":
            self.board.revealed.add(ch)
        self.board.update_display()

    def tossup_reveal_step(self) -> None:
        # reveal a random unrevealed letter *position* (if any)
        if not self.board.puzzle:
            self._tossup_timer.stop()
            return

        # build list of indices that are letters and not yet revealed
        remaining_indices: list[int] = [
            i
            for i, ch in enumerate(self.board.correct_letters)
            if ch.isalpha() and i not in self.board._revealed_positions
            # don't check ch in self.board.revealed here because we want
            # tossup reveals to be per-instance even if the same letter already guessed
        ]

        if not remaining_indices:
            # nothing left to reveal
            self._tossup_timer.stop()
            return

        # reveal exactly one random position
        idx: int = random.choice(remaining_indices)
        self.board._revealed_positions.add(idx)
        self.board.update_display()

    def pause_tossup(self) -> None:
        self.sounds.play("LETTER_REVEAL")
        # Pause reveals
        if self._tossup_timer.isActive():
            self._tossup_timer.stop()
            self.tossup_paused = True

        self.pause_dlg: QtWidgets.QDialog = QtWidgets.QDialog(self)
        layout: QtWidgets.QVBoxLayout = QtWidgets.QVBoxLayout()
        self.pause_dlg.setWindowTitle("Solve?")
        self.players_list: QtWidgets.QComboBox = QtWidgets.QComboBox()
        self.players_list.addItems([p.name for p in self.players])
        self.current_player_index = self.players_list.currentIndex()
        self.players_list.currentIndexChanged.connect(
            lambda _: setattr(
                self, "current_player_index", self.players_list.currentIndex()
            )
        )
        correct_tossup_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Correct")
        incorrect_tossup_btn: QtWidgets.QPushButton = QtWidgets.QPushButton("Incorrect")
        layout.addWidget(self.players_list)
        layout.addWidget(correct_tossup_btn)
        layout.addWidget(incorrect_tossup_btn)
        self.pause_dlg.setLayout(layout)
        correct_tossup_btn.clicked.connect(self.solve_and_reveal)
        incorrect_tossup_btn.clicked.connect(self.incorrect_solve)
        self.pause_dlg.setModal(True)
        self.pause_dlg.show()

    def do_spin(self) -> None:
        # Host initiates a spin on behalf of current player
        if not self.players[self.current_player_index].has_spun:
            self.spin_btn.setEnabled(False)
            self.solve_btn.setEnabled(False)
            [x.setEnabled(False) for x in self.letter_buttons.values()]
            self.wheel.spin()

    def on_wheel_result(self, result) -> None:
        wedge: str = result["value"]
        # reset last_spin_value by default
        self.last_spin_value = None

        # handle wedge outcomes
        if wedge == "BANKRUPT":
            self.players[self.current_player_index].set_bankrupt()
            self.sounds.play("BANKRUPT")
            self.status_label.setText(
                f"{self.players[self.current_player_index].name}: BANKRUPT! :("
            )
            self._advance_turn()
        elif wedge == "LOSE A TURN":
            self.sounds.play("INCORRECT")
            self.status_label.setText(
                f"{self.players[self.current_player_index].name}: LOST A TURN! :("
            )
            self._advance_turn()
        else:
            # monetary wedge: set last_spin_value and instruct host to pick a consonant
            try:
                amount = float(wedge)
            except Exception:
                amount = 0.0
            self.last_spin_value = amount
            self.status_label.setText(
                f"{self.players[self.current_player_index].name}: {fmt_money(amount)}"
            )
            self.solve_btn.setEnabled(True)
            # Enable letter buttons that are not revealed
            for ch, btn in self.letter_buttons.items():
                if ch not in self.board.revealed and (
                    ch not in "AEIOU"
                    or self.players[self.current_player_index].round_score > VOWEL_COST
                ):
                    btn.setEnabled(True)
            if self.current_phase == "FINAL SPIN":
                self.sounds.play("SPEED_UP")
        self._update_player_scores_ui()

    def _advance_turn(self) -> None:
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        self.spin_btn.setEnabled(True)
        self.status_label.setText(
            f"Turn: {self.players[self.current_player_index].name}"
        )

    def on_letter_selected(self, ch: str) -> None:
        # disable chosen button immediately (can't pick same letter twice)
        if ch in self.letter_buttons:
            self.letter_buttons[ch].setEnabled(False)

        count: int = self.board.guess_letter(ch)
        if count > 0:
            if ch in "AEIOU":
                self.players[self.current_player_index].round_score -= VOWEL_COST
            else:
                gained: float = self.last_spin_value * count
                self.players[self.current_player_index].add_money(gained)

        self._advance_turn()
        if not self.current_phase == "FINAL SPIN":
            self.last_spin_value = None
        self._update_player_scores_ui()

    def solve_and_reveal(self) -> None:
        # Host marks the current player's attempt as correct
        self.solve_btn.setEnabled(False)
        if self.current_phase == "TOSS-UP" and self.pause_dlg.isVisible():
            self.pause_dlg.accept()
        if self.current_phase == "MAIN" and self.solve_dlg.isVisible():
            self.solve_dlg.accept()
        if self.current_phase == "TOSS-UP":
            self.sounds.stop("TOSS-UP")
            self.sounds.play("TOSS-UP_SOLVE")
            self.players[self.current_player_index].add_money(
                self.puzzle_class.get_prize_value(self.current_puzzle_index)
            )
        self.players[self.current_player_index].total_score += self.players[
            self.current_player_index
        ].round_score
        self.board.reveal_all()
        if self.current_phase != "TOSS-UP":
            self.sounds.play("PUZZLE_SOLVE")
        self._end_round_for_player(self.players[self.current_player_index])
        self._update_player_scores_ui()
        self.next_puzzle_btn.setEnabled(True)
        if self.current_phase == "FINAL SPIN":
            self.sounds.stop("SPEED_UP")
            top: Player = max(self.players, key=lambda x: x.total_score)
            QtWidgets.QMessageBox.information(
                self,
                "Bonus Round",
                f"{top.name} will play the Bonus Round!",
            )
        if self.current_phase == "BONUS ROUND":
            self.sounds.stop("COUNTDOWN")
            self._show_final_results()

    def incorrect_solve(self) -> None:
        # Host marks the current player's attempt as incorrect
        if self.current_phase == "TOSS-UP" and self.pause_dlg.isVisible():
            self.pause_dlg.reject()
        elif self.solve_dlg.isVisible():
            self.solve_dlg.reject()
        self.sounds.play("INCORRECT")
        # For toss-ups: decrement tossup attempts/allow next buzz; for main rounds treat as normal incorrect
        if self.current_phase == "TOSS-UP":
            # incorrect on toss-up — continue toss-up (resume reveal)
            self.status_label.setText("Incorrect! Toss-Up Resumes in 3 Seconds!")
            QtCore.QTimer.singleShot(3000, self._resume_tossup_reveal)
        else:
            self._advance_turn()
        self._update_player_scores_ui()

    def _resume_tossup_reveal(self) -> None:
        if not self._tossup_timer.isActive():
            self._tossup_timer.start()
            self.tossup_paused = False

    def _end_round_for_player(self, player: Player) -> None:
        if self.round_number < len(self.puzzles):
            self.status_label.setText(
                f"{player.name} Has Solved The Puzzle! Round Score: {fmt_money(player.round_score)}"
            )
            for p in self.players:
                p.round_score = 0.0
        self._update_player_scores_ui()

    def _show_final_results(self) -> None:
        self.sounds.play("THEME")
        scores: list[Player] = sorted(
            self.players, key=lambda p: p.total_score, reverse=True
        )
        txt = "Final Standings:\n"
        for p in scores:
            txt += f"{p.name}: {fmt_money(p.total_score)}\n"
        QtWidgets.QMessageBox.information(self, "Thanks For Playing!", txt)
        self.status_label.setText("Game Over")

    def override_score(self) -> None:
        idx: int = self.override_player_cb.currentIndex()
        p: Player = self.players[idx]
        p.round_score = self.override_round_spin.value()
        p.total_score = self.override_total_spin.value()
        self._update_player_scores_ui()
        QtWidgets.QMessageBox.information(
            self, "Success", f"{p.name}'s scores updated."
        )

    def host_set_turn(self, idx: int) -> None:
        # Host sets whose turn it is
        self.current_player_index = idx
        self.status_label.setText(f"Turn: {self.players[idx].name}")
