from typing import Callable, Optional


class AppLogger:
    def __init__(self, gui_callback: Optional[Callable[[str], None]] = None):
        self.gui_callback = gui_callback

    def _emit(self, level: str, message: str) -> None:
        line = f"[{level}] {message}"
        print(line)
        if self.gui_callback:
            self.gui_callback(line)

    def info(self, message: str) -> None:
        self._emit("INFO", message)

    def warning(self, message: str) -> None:
        self._emit("WARN", message)

    def error(self, message: str) -> None:
        self._emit("ERROR", message)