import socket
import threading
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class RobotState:
    connected: bool = False
    busy: bool = False
    pos_x: float = 0.0
    pos_y: float = 0.0
    pos_z: float = 0.0


class RobotController:
    def __init__(
        self,
        config,
        logger,
        on_state_change: Optional[Callable[[RobotState], None]] = None,
        on_response: Optional[Callable[[str], None]] = None,
    ):
        self.cfg = config
        self.logger = logger
        self.on_state_change = on_state_change
        self.on_response = on_response

        self._state = RobotState()
        self._sock: Optional[socket.socket] = None
        self._lock = threading.Lock()

    def _log(self, message: str) -> None:
        self.logger.info(message)

    def _warn(self, message: str) -> None:
        self.logger.warning(message)

    def _error(self, message: str) -> None:
        self.logger.error(message)

    def _notify(self) -> None:
        if self.on_state_change:
            self.on_state_change(self.get_state())

    def get_state(self) -> RobotState:
        with self._lock:
            return RobotState(
                connected=self._state.connected,
                busy=self._state.busy,
                pos_x=self._state.pos_x,
                pos_y=self._state.pos_y,
                pos_z=self._state.pos_z,
            )

    def is_connected(self) -> bool:
        return self.get_state().connected

    def is_busy(self) -> bool:
        return self.get_state().busy

    def connect(self) -> bool:
        with self._lock:
            if self._state.connected:
                return True

        try:
            self._log(f"Conectando a {self.cfg.robot_ip}:{self.cfg.robot_port}...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((self.cfg.robot_ip, self.cfg.robot_port))
            sock.settimeout(None)
            self._sock = sock

            with self._lock:
                self._state.connected = True
                self._state.busy = False

            self._log("Conexión establecida.")
            self._notify()

            threading.Thread(target=self._listen_robot, daemon=True).start()
            return True

        except Exception as e:
            self._error(f"Falló la conexión: {e}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        with self._lock:
            self._state.connected = False
            self._state.busy = False
            sock = self._sock
            self._sock = None

        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                sock.close()
            except Exception:
                pass

        self._log("Desconectado.")
        self._notify()

    def send_text(self, text: str) -> bool:
        with self._lock:
            if not self._state.connected or self._sock is None:
                self._warn("No hay conexión activa.")
                return False
            sock = self._sock

        try:
            sock.sendall(text.encode("utf-8"))
            self._log(f"Enviado: {text}")
            return True
        except Exception as e:
            self._error(f"Error al enviar comando: {e}")
            self.disconnect()
            return False

    def send_command(self, command: str) -> bool:
        with self._lock:
            if not self._state.connected:
                self._warn("No se puede enviar comando sin conexión.")
                return False
            self._state.busy = True

        self._notify()
        ok = self.send_text(command)

        if not ok:
            with self._lock:
                self._state.busy = False
            self._notify()

        return ok

    def _listen_robot(self) -> None:
        while True:
            with self._lock:
                connected = self._state.connected
                sock = self._sock

            if not connected or sock is None:
                break

            try:
                data = sock.recv(1024)
                if not data:
                    self._warn("El robot cerró la conexión.")
                    self.disconnect()
                    break

                response = data.decode("latin-1", errors="ignore").strip()
                if response:
                    self._process_response(response)

            except Exception as e:
                self._error(f"Error escuchando al robot: {e}")
                self.disconnect()
                break

    def _process_response(self, response: str) -> None:
        with self._lock:
            if "FIN:" in response or "ALERTA:" in response:
                self._state.busy = False

            if "INC:" in response:
                parts = response.split()
                try:
                    value = float(parts[1])
                    axis = parts[3]
                    if axis == "X":
                        self._state.pos_x += value
                    elif axis == "Y":
                        self._state.pos_y += value
                    elif axis == "Z":
                        self._state.pos_z += value
                except Exception:
                    pass

            elif "HOME" in response:
                self._state.pos_x = 0.0
                self._state.pos_y = 0.0
                self._state.pos_z = 0.0

            elif "INICIO" in response:
                self._state.pos_x = 0.0
                self._state.pos_y = 0.0
                self._state.pos_z = -20.0

        if self.on_response:
            self.on_response(response)

        self._log(f"Robot: {response}")
        self._notify()