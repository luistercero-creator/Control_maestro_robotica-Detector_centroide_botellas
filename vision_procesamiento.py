import os
from dataclasses import dataclass

import cv2
import numpy as np
from keras.models import load_model


@dataclass
class VisionAnalysis:
    detected: bool = False
    aligned: bool = False
    confidence: float = 0.0
    error_robot_x: float = 0.0
    error_robot_y: float = 0.0
    status_text: str = "BUSCANDO BOTELLA..."


class VisionProcessor:
    def __init__(self, config, logger):
        self.cfg = config
        self.logger = logger

        self._model = None
        self._class_names = []
        self._smooth_x = 0
        self._smooth_y = 0
        self._smooth_r = 0

    def _log(self, message: str) -> None:
        self.logger.info(message)

    def _error(self, message: str) -> None:
        self.logger.error(message)

    def load_model(self) -> bool:
        try:
            if not os.path.exists(self.cfg.model_path):
                raise FileNotFoundError(self.cfg.model_path)

            if not os.path.exists(self.cfg.labels_path):
                raise FileNotFoundError(self.cfg.labels_path)

            self._model = load_model(self.cfg.model_path, compile=False)
            with open(self.cfg.labels_path, "r", encoding="utf-8") as f:
                self._class_names = f.readlines()

            self._log("IA cargada correctamente.")
            return True

        except Exception as e:
            self._error(f"No se pudo cargar la IA: {e}")
            return False

    def _reset_smoothing(self) -> None:
        self._smooth_x = 0
        self._smooth_y = 0
        self._smooth_r = 0

    def process_frame(self, frame):
        if self._model is None:
            return frame, VisionAnalysis(status_text="MODELO NO CARGADO")

        img = frame.copy()
        h, w = img.shape[:2]
        cx = w // 2
        cy = h // 2

        cv2.line(img, (cx, 0), (cx, h), (200, 200, 200), 1)
        cv2.line(img, (0, cy), (w, cy), (200, 200, 200), 1)
        cv2.circle(img, (cx, cy), self.cfg.center_tolerance_px, (255, 255, 0), 1)

        resized = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
        arr = np.asarray(resized, dtype=np.float32).reshape(1, 224, 224, 3)
        norm = (arr / 127.5) - 1

        pred = self._model.predict(norm, verbose=0)
        idx = int(np.argmax(pred))
        confidence = float(pred[0][idx])
        class_name = self._class_names[idx].strip() if self._class_names else ""

        analysis = VisionAnalysis(confidence=confidence, status_text="BUSCANDO BOTELLA...")

        if "0" not in class_name or confidence <= self.cfg.confidence_threshold:
            self._reset_smoothing()
            cv2.putText(img, analysis.status_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.putText(img, f"Confianza IA: {confidence * 100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            return img, analysis

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        blurred = cv2.medianBlur(hsv, 7)

        lower_cap = np.array([100, 80, 20])
        upper_cap = np.array([130, 255, 255])
        mask = cv2.inRange(blurred, lower_cap, upper_cap)

        kernel = np.ones((11, 11), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        circles = cv2.HoughCircles(
            mask,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=100,
            param1=50,
            param2=18,
            minRadius=15,
            maxRadius=200,
        )

        if circles is None:
            self._reset_smoothing()
            analysis.status_text = "CALCULANDO GEOMETRÍA..."
            cv2.putText(img, analysis.status_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(img, f"Confianza IA: {confidence * 100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            return img, analysis

        circles = np.round(circles[0, :]).astype("int")
        x_raw, y_raw, r_raw = circles[0]

        if self._smooth_x == 0:
            self._smooth_x = x_raw
            self._smooth_y = y_raw
            self._smooth_r = r_raw
        else:
            a = self.cfg.smoothing_factor
            self._smooth_x = int((x_raw * a) + (self._smooth_x * (1.0 - a)))
            self._smooth_y = int((y_raw * a) + (self._smooth_y * (1.0 - a)))
            self._smooth_r = int((r_raw * a) + (self._smooth_r * (1.0 - a)))

        error_cam_x = self._smooth_x - cx
        error_cam_y = self._smooth_y - cy

        if self.cfg.camera_rotated_90:
            error_robot_x = error_cam_y * self.cfg.invert_robot_x
            error_robot_y = error_cam_x * self.cfg.invert_robot_y
        else:
            error_robot_x = error_cam_x * self.cfg.invert_robot_x
            error_robot_y = error_cam_y * self.cfg.invert_robot_y

        aligned = (
            abs(error_robot_x) <= self.cfg.center_tolerance_px
            and abs(error_robot_y) <= self.cfg.center_tolerance_px
        )

        analysis.detected = True
        analysis.aligned = aligned
        analysis.error_robot_x = float(error_robot_x)
        analysis.error_robot_y = float(error_robot_y)

        cv2.circle(img, (self._smooth_x, self._smooth_y), self._smooth_r, (255, 0, 255), 3)
        cv2.drawMarker(img, (self._smooth_x, self._smooth_y), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
        cv2.line(img, (cx, cy), (self._smooth_x, self._smooth_y), (0, 165, 255), 2)

        if aligned:
            analysis.status_text = "ALINEADO PERFECTAMENTE"
            color = (0, 255, 0)
        else:
            analysis.status_text = f"CORREGIR -> X: {-error_robot_x}px | Y: {-error_robot_y}px"
            color = (0, 165, 255)

        cv2.putText(img, analysis.status_text, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(img, f"Confianza IA: {confidence * 100:.0f}%", (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        return img, analysis