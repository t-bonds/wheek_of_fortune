from PySide6 import QtWidgets, QtGui, QtCore
from data import Puzzle


class BoardWidget(QtWidgets.QWidget):
    class BoardDisplay(QtWidgets.QWidget):
        """
        Custom widget that paints the puzzle phrase, underscores, and temporary blue
        reveal rectangles. It reads state from the enclosing BoardWidget instance.
        """

        def __init__(self, owner: "BoardWidget", parent=None) -> None:
            super().__init__(parent)
            self.owner = owner
            # enable high-DPI crisp painting
            self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent)
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding
            )

        def sizeHint(self) -> QtCore.QSize:
            return QtCore.QSize(600, 160)

        def minimumSizeHint(self) -> QtCore.QSize:
            return QtCore.QSize(200, 100)

        def paintEvent(self, event: QtGui.QPaintEvent) -> None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.TextAntialiasing)

            # Background (transparent so parent controls background)
            painter.fillRect(event.rect(), self.palette().window())

            widget_w = self.width()
            widget_h = self.height()
            fm = QtGui.QFontMetrics(self.owner._display_font)

            # Use line spacing with a tiny bit of extra vertical padding
            line_height = fm.lineSpacing() + 6
            x_margin = 12
            y_margin = 8

            phrase = self.owner.puzzle.phrase if self.owner.puzzle else ""
            # For monospace fonts, using the width of "M" is reliable for cell width
            cell_w = max(fm.horizontalAdvance("M"), fm.horizontalAdvance("_")) + int(
                fm.averageCharWidth() * 0.6
            )
            gap = int(cell_w * 0.15)

            # --- Determine wrapping: produce list of lines, each line is list of (index, char) ---
            lines: list[list[tuple[int, str]]] = []
            current_line: list[tuple[int, str]] = []
            cur_x = x_margin

            for i, ch in enumerate(phrase):
                # if next cell would overflow, push current line and start a new one
                if cur_x + cell_w + x_margin > widget_w and current_line:
                    lines.append(current_line)
                    current_line = []
                    cur_x = x_margin

                current_line.append((i, ch))
                cur_x += cell_w + gap

            if current_line:
                lines.append(current_line)

            # compute vertical centering
            line_count = max(1, len(lines))
            total_height = line_count * line_height
            start_top = max(y_margin, (widget_h - total_height) / 2)

            # draw each line
            for line_idx, line in enumerate(lines):
                y = start_top + line_idx * line_height + fm.ascent()
                x = x_margin

                for index, ch in line:
                    rect = QtCore.QRectF(x, y - fm.ascent(), cell_w, fm.height())

                    if not ch.isalpha():
                        # draw non-alpha characters directly (like spaces, punctuation)
                        painter.setFont(self.owner._display_font)
                        painter.setPen(self.owner._text_pen)
                        painter.drawText(rect, QtCore.Qt.AlignCenter, ch)
                    else:
                        # overlay (blue rectangle) takes precedence
                        if index in self.owner._overlay_positions:
                            # draw rounded blue rectangle
                            painter.setBrush(self.owner._blue_brush)
                            painter.setPen(QtCore.Qt.NoPen)
                            # shrink rect a bit for padding
                            r = rect.adjusted(3, 3, -3, -5)
                            painter.drawRoundedRect(r, 6, 6)
                        # DRAW BY POSITION: only draw the revealed letter for this specific index
                        elif index in self.owner._revealed_positions:
                            painter.setFont(self.owner._display_font)
                            painter.setPen(self.owner._text_pen)
                            painter.drawText(rect, QtCore.Qt.AlignCenter, ch.upper())
                        # fallback: if letter is present in revealed-letters set (older logic),
                        # show it when finalized — keeps backwards compatibility
                        elif (
                            ch.upper() in self.owner.revealed
                            and self.owner._finalize_flag
                        ):
                            painter.setFont(self.owner._display_font)
                            painter.setPen(self.owner._text_pen)
                            painter.drawText(rect, QtCore.Qt.AlignCenter, ch.upper())
                        else:
                            # decide whether to draw underscore or blank space depending on animation state
                            if (
                                self.owner._anim_active
                                and index >= self.owner._anim_index
                                and not self.owner._finalize_flag
                            ):
                                # blank space to keep spacing while animating (draw nothing)
                                pass
                            else:
                                # show underscore (unrevealed)
                                painter.setFont(self.owner._display_font)
                                painter.setPen(self.owner._text_pen)
                                # draw a small underscore centered horizontally near the bottom of rect
                                underscore_y = rect.bottom() - 5
                                us_w = max(10, cell_w * 0.65)
                                us_x = rect.x() + (cell_w - us_w) / 2
                                painter.drawLine(
                                    QtCore.QPointF(us_x, underscore_y),
                                    QtCore.QPointF(us_x + us_w, underscore_y),
                                )

                    x += cell_w + gap

            painter.end()

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.puzzle: Puzzle | None = None
        self.revealed: set[str] = set()
        self.correct_letters: set[str] = set()

        # track revealed *positions* (indexes) separately from revealed letters
        self._revealed_positions: set[int] = set()

        self.parent = parent
        self.sounds = getattr(self.parent, "sounds", None)

        # Animation and reveal timers
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.timeout.connect(self._animate_step)
        self._anim_index = 0
        self._anim_delay_ms = 100  # ms between showing each placeholder
        self._anim_active = False
        self._finalize_flag = False  # used by display to emulate finalize param

        # blue-square placement timer (cadence for when blue squares appear)
        self._blue_timer = QtCore.QTimer(self)
        self._blue_timer.timeout.connect(self._place_next_blue)

        # positions waiting to have their blue squares placed (queue)
        self._positions_to_place: list[int] = []
        # map pos -> single-shot timer converting blue->letter (so we can cancel if needed)
        self._blue_to_letter_timers: dict[int, QtCore.QTimer] = {}

        # Internal overlay positions (integers) representing positions currently showing blue rectangle
        self._overlay_positions: set[int] = set()

        # Visual resources
        # Use a monospace/fixed-pitch font for perfectly even cells.
        # "Courier New" is commonly available; also set style hint and fixed pitch for reliability.
        self._display_font = QtGui.QFont("Courier New", 20)
        self._display_font.setStyleHint(QtGui.QFont.Monospace)
        self._display_font.setFixedPitch(True)
        self._display_font.setBold(True)

        # keep category label as a distinct (non-mono) font for readability
        self._category_font = QtGui.QFont("Helvetica", 12)
        self._category_font.setItalic(True)

        # TEXT COLOR: white
        self._text_pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
        self._blue_brush = QtGui.QBrush(QtGui.QColor("#2A6FB8"))

        self._init_ui()

    def _init_ui(self) -> None:
        # category QLabel on top, BoardDisplay below
        self.category_label = QtWidgets.QLabel("")
        self.category_label.setFont(self._category_font)
        self.category_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        # Category label text should also be white to match the board
        palette = self.category_label.palette()
        palette.setColor(
            self.category_label.foregroundRole(), QtGui.QColor(255, 255, 255)
        )
        self.category_label.setPalette(palette)

        self.display = BoardWidget.BoardDisplay(self)
        self.display.setFont(self._display_font)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.category_label)
        layout.addWidget(self.display)
        layout.setStretch(0, 0)
        layout.setStretch(1, 1)
        self.setLayout(layout)
        self.setMinimumHeight(160)

    # ----- API-compatible methods (keep same signatures where possible) -----
    def load_puzzle(self, puzzle: Puzzle) -> None:
        self.puzzle = puzzle
        self.revealed = set()
        # clear per-position reveals
        self._revealed_positions.clear()

        # set of letters that need to be revealed to solve
        self.correct_letters = set(ch.upper() for ch in puzzle.phrase if ch.isalpha())

        self._overlay_positions.clear()
        # stop any in-flight blue placement or conversion timers
        self._stop_all_reveal_timers()

        self._positions_to_place = []
        self._reveal_index = 0
        self._reveal_phase = 0

        self._anim_index = 0
        self._anim_active = True
        self._finalize_flag = False

        if self._anim_timer.isActive():
            self._anim_timer.stop()
        self._anim_timer.start(self._anim_delay_ms)

        if self.sounds:
            try:
                self.sounds.play("PUZZLE_REVEAL")
            except Exception:
                pass

        self.category_label.setText(f"Category: {self.puzzle.category}")
        self._render_display()

    def guess_letter(self, ch: str) -> int:
        # stop any ongoing entrance animation immediately
        if self._anim_timer.isActive():
            self._anim_timer.stop()
            self._anim_active = False
            self._finalize_flag = True
            self._render_display(finalize=True)

        # if a reveal animation is running, finalize it
        if self._blue_timer.isActive() or self._blue_to_letter_timers:
            # finalize current animation first so guesses behave deterministically
            self._finalize_reveal_animation()

        ch = ch.upper()
        if ch in self.correct_letters and ch not in self.revealed:
            positions = [i for i, c in enumerate(self.puzzle.phrase) if c.upper() == ch]
            count = len(positions)
            # use default timing values; callers may override parameters if desired
            self.start_reveal_animation(
                positions,
                per_step_ms=2000,
                initial_delay_ms=1000,
                blue_to_letter_ms=3000,
            )
            return count
        self.sounds.play("INCORRECT")
        return 0

    def is_solved(self) -> bool:
        return self.correct_letters.issubset(self.revealed)

    def update_display(self) -> None:
        if self._anim_timer.isActive():
            self._anim_timer.stop()
            self._anim_active = False
        if self._blue_timer.isActive() or self._blue_to_letter_timers:
            self._finalize_reveal_animation()
        if not self.puzzle:
            self.category_label.setText("")
            self.display.update()
            return
        self._finalize_flag = True
        self._render_display(finalize=True)

    def _render_display(self, finalize: bool = False) -> None:
        """
        Trigger repaint of the display. finalize=True will cause underscores to be shown for
        unrevealed letters (used when an animation is interrupted or finished).
        """
        self._finalize_flag = bool(finalize)
        if self.puzzle:
            self.category_label.setText(f"Category: {self.puzzle.category}")
        self.display.update()

    def reveal_all(self) -> None:
        if not self.puzzle:
            return
        if self._anim_timer.isActive():
            self._anim_timer.stop()
            self._anim_active = False
        if self._blue_timer.isActive() or self._blue_to_letter_timers:
            self._finalize_reveal_animation()
        # reveal letters (keeps other code that expects letter-set working)
        self.revealed = set(ch.upper() for ch in self.puzzle.phrase if ch.isalpha())
        # NEW: reveal all positions too
        self._revealed_positions = set(
            i for i, ch in enumerate(self.puzzle.phrase) if ch.isalpha()
        )
        self._render_display(finalize=True)

    def start_reveal_animation(
        self,
        positions: list[int],
        per_step_ms: int = 3000,
        initial_delay_ms: int | None = None,
        blue_to_letter_ms: int | None = None,
    ) -> None:
        """
        Begin the reveal animation for a list of positions (left->right).

        Timing semantics:
          - initial_delay_ms: how long before the first blue square is placed.
                              If None, defaults to 1000 ms.
          - per_step_ms: how long between placing successive blue squares (cadence).
          - blue_to_letter_ms: how long after a blue square is placed that it converts to the letter.

        Important: conversion of a given blue square to its letter is independent of when
        other blue squares are placed. Each blue square schedules its own single-shot
        timer to convert after blue_to_letter_ms.
        """
        if not positions:
            return

        # sort positions left->right
        self._positions_to_place = sorted(positions)
        # clear any previous state for overlays / scheduled conversions
        self._overlay_positions.clear()
        self._stop_all_reveal_timers()

        # store these timing values so other methods can reference them if needed
        self._current_per_step_ms = per_step_ms
        self._current_blue_to_letter_ms = blue_to_letter_ms

        # prepare blue placement timer but don't start it yet
        self._blue_timer.setInterval(per_step_ms)

        # Start the sequence after initial_delay_ms. We place the first blue immediately when the initial delay fires,
        # then the _blue_timer will keep placing more at `per_step_ms`.
        def _begin_sequence():
            # place first blue immediately
            self._place_next_blue()
            # if there are still positions remaining, start repeating timer for subsequent placements
            if self._positions_to_place:
                # start regular cadence for remaining placements
                self._blue_timer.start(per_step_ms)

        # Use singleShot for the initial delay so placement cadence is independent
        if initial_delay_ms <= 0:
            _begin_sequence()
        else:
            QtCore.QTimer.singleShot(initial_delay_ms, _begin_sequence)

        # initial render so the UI can show the impending animation
        self._render_display()

    # ----- blue placement & conversion helpers -----
    def _place_next_blue(self) -> None:
        """
        Place a blue rectangle at the next position in the queue and schedule its conversion
        to the letter after `_current_blue_to_letter_ms`. This is called by the repeating
        _blue_timer (and once immediately after the initial delay).
        """
        if not self._positions_to_place:
            # nothing left to place; stop the cadence timer
            if self._blue_timer.isActive():
                self._blue_timer.stop()
            return

        pos = self._positions_to_place.pop(0)
        self._overlay_positions.add(pos)
        # play sound for blue pop
        if self.sounds:
            try:
                self.sounds.play("LETTER_REVEAL")
            except Exception:
                pass
        self._render_display()

        # schedule conversion of this blue -> letter after configured delay
        conv_timer = QtCore.QTimer(self)
        conv_timer.setSingleShot(True)

        # use a bound method to capture pos in closure
        conv_timer.timeout.connect(lambda p=pos: self._convert_blue_to_letter(p))
        conv_timer.start(self._current_blue_to_letter_ms)
        # track it so we can cancel if needed
        self._blue_to_letter_timers[pos] = conv_timer

        # if we've just placed the last blue, stop the cadence timer (it may already be stopped)
        if not self._positions_to_place and self._blue_timer.isActive():
            self._blue_timer.stop()

    def _convert_blue_to_letter(self, pos: int) -> None:
        """
        Convert a blue overlay at position `pos` into the revealed letter.
        This method is called by each conversion timer when it fires.
        """
        if not self.puzzle:
            return

        # mark that position revealed
        self._revealed_positions.add(pos)
        # remove overlay if present
        if pos in self._overlay_positions:
            self._overlay_positions.remove(pos)

        # cleanup and remove the conversion timer entry if it exists
        timer = self._blue_to_letter_timers.pop(pos, None)
        if timer and timer.isActive():
            timer.stop()

        # Also, if all positions for this particular letter are now revealed, add the letter
        ch = self.puzzle.phrase[pos]
        letter = ch.upper()
        positions_for_letter = [
            i for i, c in enumerate(self.puzzle.phrase) if c.upper() == letter
        ]
        if all(p in self._revealed_positions for p in positions_for_letter):
            self.revealed.add(letter)

        self._render_display()

        # if no more active overlays/conversions and no positions queued, finalize automatically
        if (
            not self._overlay_positions
            and not self._positions_to_place
            and not self._blue_to_letter_timers
        ):
            self._finalize_reveal_animation()

    def _stop_all_reveal_timers(self) -> None:
        """
        Stop and clear any active timers used in the reveal pipeline:
         - repeating blue placement timer
         - per-position conversion timers
        """
        if self._blue_timer.isActive():
            self._blue_timer.stop()

        # stop and delete all single-shot timers
        for t in list(self._blue_to_letter_timers.values()):
            try:
                if t.isActive():
                    t.stop()
            except Exception:
                pass
        self._blue_to_letter_timers.clear()

    # ----- timers callbacks -----
    def _animate_step(self) -> None:
        """
        Timer tick: reveal the next placeholder (underscore) from left to right.
        """
        if not self.puzzle:
            self._anim_timer.stop()
            self._anim_active = False
            return

        phrase = self.puzzle.phrase

        # Advance the animation index by one position (one tick shows one more character)
        if self._anim_index < len(phrase):
            self._anim_index += 1

        # Re-render according to animation progress
        self._render_display()

        # If we've animated across the entire phrase, stop and finalize the display
        if self._anim_index >= len(phrase):
            self._anim_timer.stop()
            self._anim_active = False
            self._finalize_flag = True
            self._render_display(finalize=True)

    # legacy method retained but not used with new flow
    def _reveal_step(self) -> None:
        # kept for backward compatibility; no-op in new system (we use _place_next_blue/_convert_blue_to_letter)
        return

    def _finalize_reveal_animation(self) -> None:
        """
        Immediately finalize/abort any running reveal animation:
          - stop cadence timer
          - stop and clear conversion timers
          - reveal all positions that were queued/overlayed so the board shows letters
        """
        # stop cadence and per-position timers
        self._stop_all_reveal_timers()

        # convert any overlayed positions to revealed positions immediately
        # and also convert any queued positions (not yet overlayed) so finalize shows them
        all_positions = set(self._overlay_positions) | set(self._positions_to_place)
        # also include any conversion timers' keys just in case
        all_positions |= set(self._blue_to_letter_timers.keys())

        if self.puzzle:
            for pos in all_positions:
                # don't call _convert_blue_to_letter (it manipulates timers); just mark revealed
                self._revealed_positions.add(pos)

        # clear overlays and queues
        self._overlay_positions.clear()
        self._positions_to_place = []
        self._blue_to_letter_timers.clear()

        self._reveal_index = 0
        self._reveal_phase = 0
        self._finalize_flag = True
        self._render_display(finalize=True)
