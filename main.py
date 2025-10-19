import sys
from PySide6 import QtWidgets
from widgets import GameWindow


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    w = GameWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
