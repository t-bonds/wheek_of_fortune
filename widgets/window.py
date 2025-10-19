import sys
import random
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets

sys.path.append(str(Path(__file__).parent.parent.resolve()))

from widgets import SoundsManager, WheelWidget, BoardWidget
from data import Puzzles, Players
from utils import fmt_money

from data import VOWEL_COST, Puzzle, Player


class GameWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wheel of Fortune")
        self.resize(1200, 720)

        # Sound manager
        self.sounds = SoundsManager()

        # Puzzles & game state
        self.puzzle_class = Puzzles()
        self.puzzles = self.puzzle_class.get_puzzles()
        self.current_puzzle_index = -1
        self.current_player_index = 0
        self.round_number = 0
        self.main_rounds_total = len([x for x in self.puzzles if x.type == "MAIN"])
        self.tossups = len([x for x in self.puzzles if x.type == "TOSS-UP"])
        self.current_phase = "SETUP"

        # last spin wedge monetary value for use by letter selection
        self.last_spin_value: float | None = None

        # toss-up reveal timer + paused flag (interval settable)
        self._tossup_timer = QtCore.QTimer()
        self._tossup_timer.setInterval(1500)  # default 1500 ms
        self._tossup_timer.timeout.connect(self.tossup_reveal_step)
        self.tossup_paused = False

        self._build_ui()
        self.show_setup_dialog()

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        h = QtWidgets.QHBoxLayout()
        central.setLayout(h)

        # Left: wheel and controls
        self.wheel = WheelWidget(self)
        self.wheel.spin_finished.connect(self.on_wheel_result)
        left_v = QtWidgets.QVBoxLayout()
        left_v.addWidget(self.wheel)
        self.spin_btn = QtWidgets.QPushButton("Spin")
        self.spin_btn.clicked.connect(self.do_spin)
        left_v.addWidget(self.spin_btn)
        left_w = QtWidgets.QWidget()
        left_w.setLayout(left_v)
        h.addWidget(left_w, 2)

        # Center: board and letter-grid inputs
        center_v = QtWidgets.QVBoxLayout()
        self.board = BoardWidget(self)
        center_v.addWidget(self.board)

        # Letter grid (A-Z) for host selection
        letters_group = QtWidgets.QGroupBox("Letters")
        grid = QtWidgets.QGridLayout()
        self.letter_buttons = {}
        all_letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        cols = 9
        for idx, ch in enumerate(all_letters):
            btn = QtWidgets.QPushButton(ch)
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
        solve_h = QtWidgets.QHBoxLayout()
        self.solve_btn = QtWidgets.QPushButton("Solve")
        self.solve_btn.clicked.connect(self.solve_button_action)
        solve_h.addWidget(self.solve_btn)
        center_v.addLayout(solve_h)

        # Admin puzzle controls
        admin_h = QtWidgets.QHBoxLayout()
        self.next_puzzle_btn = QtWidgets.QPushButton("Next Puzzle")
        self.next_puzzle_btn.clicked.connect(self._next_phase)
        admin_h.addWidget(self.next_puzzle_btn)
        center_v.addLayout(admin_h)

        center_w = QtWidgets.QWidget()
        center_w.setLayout(center_v)
        h.addWidget(center_w, 3)

        # Right: players UI
        right_v = QtWidgets.QVBoxLayout()
        players_title = QtWidgets.QLabel("Players")
        players_title.setFont(QtGui.QFont("", 14, QtGui.QFont.Bold))
        right_v.addWidget(players_title)
        self.players_list_widget = QtWidgets.QVBoxLayout()
        right_v.addLayout(self.players_list_widget)

        # Admin override controls (select player, set money, undo)
        override_group = QtWidgets.QGroupBox("Override Player Score")
        ov_layout = QtWidgets.QFormLayout()
        self.override_player_cb = QtWidgets.QComboBox()
        self.override_round_spin = QtWidgets.QDoubleSpinBox()
        self.override_round_spin.setPrefix("$")
        self.override_round_spin.setMaximum(1000000)
        self.override_total_spin = QtWidgets.QDoubleSpinBox()
        self.override_total_spin.setPrefix("$")
        self.override_total_spin.setMaximum(1000000)
        apply_btn = QtWidgets.QPushButton("Apply Override")
        apply_btn.clicked.connect(self.override_score)
        ov_layout.addRow("Player:", self.override_player_cb)
        ov_layout.addRow("Round Score:", self.override_round_spin)
        ov_layout.addRow("Total Score:", self.override_total_spin)
        ov_layout.addRow(apply_btn)
        override_group.setLayout(ov_layout)
        right_v.addWidget(override_group)

        # Status label
        self.status_label = QtWidgets.QLabel("Status: Setup")
        right_v.addWidget(self.status_label)

        right_v.addStretch()
        right_w = QtWidgets.QWidget()
        right_w.setLayout(right_v)
        h.addWidget(right_w, 2)

        self.setCentralWidget(central)

    def show_setup_dialog(self) -> None:
        self.sounds.play("THEME", loop=True)
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Player Setup")
        layout = QtWidgets.QFormLayout(dlg)

        num_players_spin = QtWidgets.QSpinBox()
        num_players_spin.setMinimum(1)
        num_players_spin.setValue(3)
        layout.addRow("Number of Players:", num_players_spin)

        rounds_spin = QtWidgets.QLabel()
        rounds_spin.setText(str(self.main_rounds_total))
        layout.addRow("Main Rounds:", rounds_spin)

        tossups_spin = QtWidgets.QLabel()
        tossups_spin.setText(str(self.tossups))
        layout.addRow("Toss-Ups:", tossups_spin)

        final_spin = QtWidgets.QLabel()
        final_spin.setText(
            "True"
            if any([True if x.type == "FINAL_SPIN" else False for x in self.puzzles])
            else "False"
        )
        layout.addRow("Final Spin:", final_spin)

        bonus_round = QtWidgets.QLabel()
        bonus_round.setText(
            "True"
            if any([True if x.type == "BONUS_ROUND" else False for x in self.puzzles])
            else "False"
        )
        layout.addRow("Bonus Round:", bonus_round)

        # Create a dedicated container (widget + vbox layout) to hold dynamic name fields.
        name_container = QtWidgets.QWidget()
        name_layout = QtWidgets.QVBoxLayout()
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_container.setLayout(name_layout)
        layout.addRow(name_container)

        name_edits: list[QtWidgets.QLineEdit] = []

        def on_num_changed(v):
            target = num_players_spin.value()
            # add fields
            while len(name_edits) < target:
                le = QtWidgets.QLineEdit()
                le.setPlaceholderText(f"Player {len(name_edits) + 1}")
                name_edits.append(le)
                name_layout.addWidget(
                    QtWidgets.QLabel(f"Player {len(name_edits)} name:")
                )
                name_layout.addWidget(le)
            # remove fields
            while len(name_edits) > target:
                le = name_edits.pop()
                # remove its label and the line edit from name_layout
                # last two widgets correspond to that entry (label + edit)
                item = name_layout.takeAt(name_layout.count() - 1)
                if item and item.widget():
                    item.widget().deleteLater()
                item = name_layout.takeAt(name_layout.count() - 1)
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
            self.players = Players(players).get_players()
            self.main_rounds_total = int(rounds_spin.text())
            self.tossups = int(tossups_spin.text())
            self._rebuild_players_panel()
            self.status_label.setText("Welcome to Wheel of Fortune!")
            self.start_game()
        else:
            sys.exit(0)

    def _rebuild_players_panel(self):
        # clear layout
        while self.players_list_widget.count():
            item = self.players_list_widget.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        # recreate player rows
        self.override_player_cb.clear()
        for idx, p in enumerate(self.players):
            w = QtWidgets.QWidget()
            h = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(p.name)
            lbl.setMinimumWidth(120)
            score_lbl = QtWidgets.QLabel(
                f"Round: {fmt_money(p.round_score)} / Total: {fmt_money(p.total_score)}"
            )
            score_lbl.setObjectName(f"score_{idx}")
            # Host buzzer button (big) to indicate host wants to select that player
            set_turn_btn = QtWidgets.QPushButton("SET TURN")
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
            w = self.players_list_widget.itemAt(i).widget()
            if w:
                labels = w.findChildren(QtWidgets.QLabel)
                if len(labels) >= 2:
                    score_lbl = labels[1]
                    p = self.players[i]
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
            self.solve_dlg = QtWidgets.QDialog(self)
            layout = QtWidgets.QVBoxLayout()
            self.solve_dlg.setWindowTitle("Solve?")
            correct_tossup_btn = QtWidgets.QPushButton("Correct")
            incorrect_tossup_btn = QtWidgets.QPushButton("Incorrect")
            layout.addWidget(correct_tossup_btn)
            layout.addWidget(incorrect_tossup_btn)
            self.solve_dlg.setLayout(layout)
            correct_tossup_btn.clicked.connect(self.solve_and_reveal)
            incorrect_tossup_btn.clicked.connect(self.incorrect_solve)
            self.solve_dlg.setModal(True)
            self.solve_dlg.show()

    def start_game(self) -> None:
        self.sounds.stop("THEME")
        self.current_player_index = 0
        self.round_number = 1
        self.status_label.setText("")
        self._next_phase()

    def _next_phase(self) -> None:
        self.board.load_puzzle(self._pop_next_puzzle())
        self.next_puzzle_btn.setEnabled(False)
        self.solve_btn.setEnabled(True)
        if self.current_phase == "TOSS-UP":
            self.go_to_tossup()
        elif self.current_phase == "MAIN":
            self._start_main_round()
        elif self.current_phase == "FINAL_SPIN":
            self._start_final_spin()
        elif self.current_phase == "BONUS_ROUND":
            self._start_bonus_round()

    def go_to_tossup(self) -> None:
        self.tossup_dlg = QtWidgets.QDialog(self)
        layout = QtWidgets.QHBoxLayout()
        self.tossup_dlg.setWindowTitle("Start Toss-Up?")
        self.start_tossup_btn = QtWidgets.QPushButton("Start")
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
        reveal_count = max(1, int(len(self.board.correct_letters) * 0.2))
        choices = [c for c in self.board.correct_letters if c not in set("AEIOU")]
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
        p = self.puzzles[self.current_puzzle_index]
        self.current_phase = p.type
        return p

    def _start_main_round(self):
        self.current_player_index = 0
        self.spin_btn.setEnabled(True)
        self.solve_btn.setEnabled(True)
        self.status_label.setText(
            f"Turn: {self.players[self.current_player_index].name}"
        )
        for p in self.players:
            p.round_score = 0.0
        self._update_player_scores_ui()

    def tossup_reveal_step(self):
        # reveal a random unrevealed consonant (if any)
        if not self.board.puzzle:
            self._tossup_timer.stop()
            return
        remaining = [
            c
            for c in self.board.correct_letters
            if c not in self.board.revealed and c not in set("AEIOU")
        ]
        if not remaining:
            # nothing left to reveal
            self._tossup_timer.stop()
            return
        # reveal one
        ch = random.choice(remaining)
        self.board.revealed.add(ch)
        self.board.update_display()

    def pause_tossup(self):
        self.sounds.play("LETTER_REVEAL")
        # Pause reveals
        if self._tossup_timer.isActive():
            self._tossup_timer.stop()
            self.tossup_paused = True

        self.pause_dlg = QtWidgets.QDialog(self)
        layout = QtWidgets.QVBoxLayout()
        self.pause_dlg.setWindowTitle("Solve?")
        self.players_list = QtWidgets.QComboBox()
        self.players_list.addItems([p.name for p in self.players])
        self.players_list.currentIndexChanged.connect(
            lambda idx: setattr(self, "current_player_index", idx)
        )
        correct_tossup_btn = QtWidgets.QPushButton("Correct")
        incorrect_tossup_btn = QtWidgets.QPushButton("Incorrect")
        layout.addWidget(self.players_list)
        layout.addWidget(correct_tossup_btn)
        layout.addWidget(incorrect_tossup_btn)
        self.pause_dlg.setLayout(layout)
        correct_tossup_btn.clicked.connect(self.solve_and_reveal)
        incorrect_tossup_btn.clicked.connect(self.incorrect_solve)
        self.pause_dlg.setModal(True)
        self.pause_dlg.show()

    def do_spin(self):
        # Host initiates a spin on behalf of current player
        current_player = self.players[self.current_player_index]
        if not current_player.has_spun:
            self.spin_btn.setEnabled(False)
            self.solve_btn.setEnabled(False)
            [x.setEnabled(False) for x in self.letter_buttons.values()]
            self.wheel.spin()

    def on_wheel_result(self, result):
        current_player = self.players[self.current_player_index]
        wedge = result["value"]
        # reset last_spin_value by default
        self.last_spin_value = None

        # handle wedge outcomes
        if wedge == "BANKRUPT":
            current_player.set_bankrupt()
            self.sounds.play("BANKRUPT")
            self.status_label.setText(f"{current_player.name}: BANKRUPT! :(")
            self._advance_turn()
        elif wedge == "LOSE A TURN":
            self.sounds.play("INCORRECT")
            self.status_label.setText(f"{current_player.name}: LOST A TURN! :(")
            self._advance_turn()
        else:
            # monetary wedge: set last_spin_value and instruct host to pick a consonant
            try:
                amount = float(wedge)
            except Exception:
                amount = 0.0
            self.last_spin_value = amount
            self.status_label.setText(f"{current_player.name}: {fmt_money(amount)}")
            self.solve_btn.setEnabled(True)
            # Enable letter buttons that are not revealed
            for ch, btn in self.letter_buttons.items():
                if ch not in self.board.revealed and (
                    ch not in "AEIOU" or current_player.round_score > VOWEL_COST
                ):
                    btn.setEnabled(True)
        self._update_player_scores_ui()

    def _advance_turn(self):
        self.current_player_index = (self.current_player_index + 1) % len(self.players)
        self.spin_btn.setEnabled(True)
        self.status_label.setText(
            f"Turn: {self.players[self.current_player_index].name}"
        )

    # ---------------------------
    # Letter grid callback
    # ---------------------------
    def on_letter_selected(self, ch: str) -> None:
        ch = ch.upper()
        current: Player = self.players[self.current_player_index]
        # disable chosen button immediately (can't pick same letter twice)
        if ch in self.letter_buttons:
            self.letter_buttons[ch].setEnabled(False)

        count = self.board.guess_letter(ch)
        if count > 0:
            if ch in "AEIOU":
                current.round_score -= VOWEL_COST
            else:
                gained = self.last_spin_value * count
                current.add_money(gained)

        self._advance_turn()
        self.last_spin_value = None
        self._update_player_scores_ui()

    # ---------------------------
    # Host adjudication
    # ---------------------------
    def solve_and_reveal(self):
        # Host marks the current player's attempt as correct

        if self.current_phase == "TOSS-UP" and self.pause_dlg.isVisible():
            self.pause_dlg.accept()
        if self.current_phase == "MAIN" and self.solve_dlg.isVisible():
            self.solve_dlg.accept()
        current = self.players[self.current_player_index]
        if self.current_phase == "TOSS-UP":
            self.sounds.stop("TOSS-UP")
            self.sounds.play("TOSS-UP_SOLVE")
            current.add_money(
                self.puzzle_class.get_prize_value(self.current_puzzle_index)
            )
            self.solve_btn.setEnabled(False)
        current.total_score += current.round_score
        self.board.reveal_all()
        if self.current_phase == "MAIN":
            self.sounds.play("PUZZLE_SOLVE")
        self._end_round_for_player(current)
        self._update_player_scores_ui()
        self.next_puzzle_btn.setEnabled(True)

    def incorrect_solve(self) -> None:
        # Host marks the current player's attempt as incorrect
        if self.current_phase == "TOSS-UP" and self.pause_dlg.isVisible():
            self.pause_dlg.reject()
        if self.solve_dlg.isVisible():
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

    # ---------------------------
    # Existing flow helpers (updated to be host-driven)
    # ---------------------------
    def _end_round_for_player(self, player: Player):
        if self.round_number < len(self.puzzles):
            self.round_number += 1
            self.status_label.setText(
                f"{player.name} Has Solved The Puzzle! Round Score: {fmt_money(player.round_score)}"
            )
            for p in self.players:
                p.round_score = 0.0
        self._update_player_scores_ui()

    def _start_final_spin(self):
        top = max(self.players, key=lambda x: x.total_score)
        QtWidgets.QMessageBox.information(
            self, "Final Spin", f"{top.name} will play the Final Spin (Bonus Round)!"
        )
        self.current_phase = "BONUS_ROUND"
        self._start_bonus_round()

    def _start_bonus_round(self):
        top = max(self.players, key=lambda x: x.total_score)
        for ch in "RSTLNE":
            self.board.revealed.add(ch)
        self.board.update_display()
        # Host picks 3 consonants and one vowel via the letter grid (host clicks them)
        QtWidgets.QMessageBox.information(
            self,
            "Bonus Round",
            f"{top.name}: Host - select 3 consonants and one vowel using the letter grid.",
        )
        # After host selection they must use the adjudication buttons to finalize
        self.current_phase = (
            "GAME_OVER"  # will be set after adjudication via host buttons
        )

    def _show_final_results(self):
        scores = sorted(self.players, key=lambda p: p.total_score, reverse=True)
        txt = "Final Standings:\n"
        for p in scores:
            txt += f"{p.name}: {fmt_money(p.total_score)}\n"
        QtWidgets.QMessageBox.information(self, "Thanks For Playing!", txt)
        self.status_label.setText("Game Over")

    def override_score(self):
        idx = self.override_player_cb.currentIndex()
        p = self.players[idx]
        p.round_score = self.override_round_spin.value()
        p.total_score = self.override_total_spin.value()
        self._update_player_scores_ui()
        QtWidgets.QMessageBox.information(
            self, "Success", f"{p.name}'s scores updated."
        )

    def host_set_turn(self, idx: int):
        # Host sets whose turn it is
        self.current_player_index = idx
        self.status_label.setText(f"Turn: {self.players[idx].name}")
