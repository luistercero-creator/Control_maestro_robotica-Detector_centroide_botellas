import threading
import time

import cv2


class CameraService:
    def __init__(self, config, vision_processor, control_logic, robot_controller, logger, on_frame):
        self.cfg = config
        self.vision = vision_processor
        self.control = control_logic
        self.robot = robot_controller
        self.logger = logger
        self.on_frame = on_frame

        self.running = False
        self.cap = None
        self.thread = None

    def _log(self, message: str) -> None:
        self.logger.info(message)

    def _warn(self, message: str) -> None:
        self.logger.warning(message)

    def start(self) -> bool:
        if self.running:
            return True

        backend = cv2.CAP_DSHOW if self.cfg.use_dshow else 0
        self.cap = cv2.VideoCapture(self.cfg.camera_index, backend)

        if not self.cap.isOpened():
            self.cap = None
            self._warn("No se pudo abrir la cámara.")
            return False

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self._log("Cámara iniciada.")
        return True

    def stop(self) -> None:
        self.running = False

        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None

    def _loop(self) -> None:
        while self.running and self.cap is not None:
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.005)
                continue

            centroid_enabled = self.control.is_centroid_enabled()
            processed_frame, analysis = self.vision.process_frame(
                frame,
                centroid_enabled=centroid_enabled,
            )

            if self.on_frame:
                self.on_frame(processed_frame, analysis)

            if self.control.auto_mode and self.robot.is_connected():
                decision = self.control.decide(analysis, self.robot.is_busy())
                if decision is not None:
                    self.logger.info(f"Decisión: {decision.reason}. Comando: {decision.command}")
                    self.robot.send_command(decision.command)

        self.stop()