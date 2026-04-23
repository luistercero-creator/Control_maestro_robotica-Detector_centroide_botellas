import socket
import threading
from typing import Callable, Optional, Dict, Any

from config import AppConfig


class RobotController:
    def __init__(
        self,
        config: AppConfig,
        logger,
        on_state_change: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.config = config
        self.logger = logger
        self.on_state_change = on_state_change

        self.sock = None
        self.connected = False
        self.robot_busy = False

        self.pos_x = 0.0
        self.pos_y = 0.0
        self.pos_z = 0.0

        self._listener_thread = None
        self._lock = threading.Lock()

    def _log(self, message: str) -> None:
        self.logger.info(message)

    def _warn(self, message: str) -> None:
        self.logger.warning(message)

    def _error(self, message: str) -> None:
        self.logger.error(message)

    def _notify_state(self) -> None:
        if self.on_state_change:
            self.on_state_change(self.get_state())

    def get_state(self) -> Dict[str, Any]:
        return {
            "connected": self.connected,
            "robot_busy": self.robot_busy,
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "pos_z": self.pos_z,
        }

    def connect(self) -> bool:
        if self.connected:
            return True

        try:
            self._log(f"Conectando a {self.config.robot_ip}:{self.config.robot_port}...")
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.config.robot_ip, self.config.robot_port))
            self.connected = True
            self._log("Conexión establecida.")
            self._notify_state()

            self._listener_thread = threading.Thread(target=self._listen_robot, daemon=True)
            self._listener_thread.start()
            return True

        except Exception as e:
            self._error(f"Falló la conexión: {e}")
            self.disconnect()
            return False

    def disconnect(self) -> None:
        with self._lock:
            self.connected = False
            self.robot_busy = False

            if self.sock is not None:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None

        self._log("Desconectado.")
        self._notify_state()

    def send_text(self, text: str) -> bool:
        if not self.connected or self.sock is None:
            self._warn("No se puede enviar el comando porque no hay conexión.")
            return False

        try:
            self.sock.send(text.encode("utf-8"))
            self._log(f"Enviado: {text}")
            return True
        except Exception as e:
            self._error(f"Error al enviar comando: {e}")
            self.disconnect()
            return False

    def send_command(self, command: str) -> bool:
        self.robot_busy = True
        self._notify_state()
        return self.send_text(command)

    def _listen_robot(self) -> None:
        while self.connected and self.sock is not None:
            try:
                data = self.sock.recv(1024)
                if not data:
                    self._warn("El robot cerró la conexión.")
                    self.disconnect()
                    break

                response = data.decode("latin-1", errors="ignore").strip()
                if response:
                    self._process_response(response)

            except Exception as e:
                if self.connected:
                    self._error(f"Error escuchando al robot: {e}")
                self.disconnect()
                break

    def _process_response(self, response: str) -> None:
        if "FIN:" in response or "ALERTA:" in response:
            self.robot_busy = False

        if "INC:" in response:
            partes = response.split()
            try:
                valor = float(partes[1])
                eje = partes[3]

                if eje == "X":
                    self.pos_x += valor
                elif eje == "Y":
                    self.pos_y += valor
                elif eje == "Z":
                    self.pos_z += valor

            except Exception:
                pass

        elif "HOME" in response:
            self.pos_x = 0.0
            self.pos_y = 0.0
            self.pos_z = 0.0

        self._log(f"Robot: {response}")
        self._notify_state()