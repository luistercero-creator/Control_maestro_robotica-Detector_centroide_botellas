import os
import threading
import numpy as np
import cv2

from keras.models import load_model

from config import AppConfig


class VisionController:
    def __init__(self, config: AppConfig, robot_controller, logger):
        self.config = config
        self.robot = robot_controller
        self.logger = logger

        self.auto_alineando = False
        self._running = False
        self._thread = None

        self._model = None
        self._class_names = []

    def _log(self, message: str) -> None:
        self.logger.info(message)

    def _warn(self, message: str) -> None:
        self.logger.warning(message)

    def _error(self, message: str) -> None:
        self.logger.error(message)

    def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._camera_loop, daemon=True)
        self._thread.start()

    def stop_auto_alignment(self) -> None:
        self.auto_alineando = False

    def toggle_auto_alignment(self) -> bool:
        self.auto_alineando = not self.auto_alineando
        return self.auto_alineando

    def _load_model(self) -> bool:
        ruta_modelo = os.path.join(self.config.project_path, "keras_model.h5")
        ruta_labels = os.path.join(self.config.project_path, "labels.txt")

        try:
            self._model = load_model(ruta_modelo, compile=False)
            with open(ruta_labels, "r", encoding="utf-8") as f:
                self._class_names = f.readlines()

            self._log("IA cargada correctamente.")
            return True

        except Exception as e:
            self._error(f"No se pudo cargar la IA: {e}")
            return False

    def _camera_loop(self) -> None:
        if not self._load_model():
            return

        backend = cv2.CAP_DSHOW if self.config.use_dshow else 0
        cap = cv2.VideoCapture(self.config.camera_index, backend)

        if not cap.isOpened():
            self._error("No se pudo abrir la cámara.")
            return

        np.set_printoptions(suppress=True)

        ancho_camara = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        alto_camara = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        centro_camara_x = ancho_camara // 2
        centro_camara_y = alto_camara // 2

        centro_suavizado_x = 0
        centro_suavizado_y = 0
        radio_suavizado = 0

        while self._running:
            ret, frame = cap.read()
            if not ret:
                self._warn("No se pudo leer un frame de la cámara.")
                break

            cv2.line(frame, (centro_camara_x, 0), (centro_camara_x, alto_camara), (200, 200, 200), 1)
            cv2.line(frame, (0, centro_camara_y), (ancho_camara, centro_camara_y), (200, 200, 200), 1)
            cv2.circle(frame, (centro_camara_x, centro_camara_y), self.config.center_tolerance_px, (255, 255, 0), 1)

            imagen_redimensionada = cv2.resize(frame, (224, 224), interpolation=cv2.INTER_AREA)
            imagen_array = np.asarray(imagen_redimensionada, dtype=np.float32).reshape(1, 224, 224, 3)
            imagen_normalizada = (imagen_array / 127.5) - 1

            prediccion = self._model.predict(imagen_normalizada, verbose=0)
            indice_ganador = np.argmax(prediccion)
            clase_ganadora = self._class_names[indice_ganador].strip()
            porcentaje_confianza = float(prediccion[0][indice_ganador])

            if "0" in clase_ganadora and porcentaje_confianza > self.config.confidence_threshold:
                hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
                blurred = cv2.medianBlur(hsv_frame, 7)

                lower_cap = np.array([100, 80, 20])
                upper_cap = np.array([130, 255, 255])
                mask_cap = cv2.inRange(blurred, lower_cap, upper_cap)

                kernel = np.ones((11, 11), np.uint8)
                mask_cap = cv2.morphologyEx(mask_cap, cv2.MORPH_CLOSE, kernel)

                circulos = cv2.HoughCircles(
                    mask_cap,
                    cv2.HOUGH_GRADIENT,
                    dp=1.2,
                    minDist=100,
                    param1=50,
                    param2=18,
                    minRadius=15,
                    maxRadius=200,
                )

                if circulos is not None:
                    circulos = np.round(circulos[0, :]).astype("int")
                    x_crudo, y_crudo, r_crudo = circulos[0]

                    if centro_suavizado_x == 0:
                        centro_suavizado_x = x_crudo
                        centro_suavizado_y = y_crudo
                        radio_suavizado = r_crudo
                    else:
                        alpha = self.config.smoothing_factor
                        centro_suavizado_x = int((x_crudo * alpha) + (centro_suavizado_x * (1.0 - alpha)))
                        centro_suavizado_y = int((y_crudo * alpha) + (centro_suavizado_y * (1.0 - alpha)))
                        radio_suavizado = int((r_crudo * alpha) + (radio_suavizado * (1.0 - alpha)))

                    error_camara_x = centro_suavizado_x - centro_camara_x
                    error_camara_y = centro_suavizado_y - centro_camara_y

                    cv2.circle(frame, (centro_suavizado_x, centro_suavizado_y), radio_suavizado, (255, 0, 255), 3)
                    cv2.drawMarker(frame, (centro_suavizado_x, centro_suavizado_y), (0, 0, 255), cv2.MARKER_CROSS, 20, 2)
                    cv2.line(frame, (centro_camara_x, centro_camara_y), (centro_suavizado_x, centro_suavizado_y), (0, 165, 255), 2)

                    if self.config.camera_rotated_90:
                        error_robot_x = error_camara_y * self.config.robot_x_inverter
                        error_robot_y = error_camara_x * self.config.robot_y_inverter
                    else:
                        error_robot_x = error_camara_x * self.config.robot_x_inverter
                        error_robot_y = error_camara_y * self.config.robot_y_inverter

                    if (
                        abs(error_robot_x) <= self.config.center_tolerance_px
                        and abs(error_robot_y) <= self.config.center_tolerance_px
                    ):
                        estado = "ALINEADO PERFECTAMENTE"
                        color_estado = (0, 255, 0)

                        if self.auto_alineando:
                            self._log("Alineación visual completada con éxito.")
                            self.auto_alineando = False
                    else:
                        estado = f"CORREGIR -> X: {-error_robot_x}px | Y: {-error_robot_y}px"
                        color_estado = (0, 165, 255)

                        if self.auto_alineando and not self.robot.robot_busy:
                            self.robot.robot_busy = True

                            if abs(error_robot_x) > self.config.center_tolerance_px:
                                mm_x = round(error_robot_x * self.config.mm_per_px, 1)
                                self._log(f"Corrigiendo eje X. Movimiento: {-mm_x} mm")
                                self.robot.send_command(f"X,{-mm_x}")

                            else:
                                mm_y = round(error_robot_y * self.config.mm_per_px, 1)
                                self._log(f"Corrigiendo eje Y. Movimiento: {-mm_y} mm")
                                self.robot.send_command(f"Y,{-mm_y}")

                    cv2.putText(frame, estado, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_estado, 2)
                    cv2.putText(
                        frame,
                        f"Confianza IA: {porcentaje_confianza * 100:.0f}%",
                        (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.6,
                        (0, 255, 0),
                        2,
                    )

                else:
                    cv2.putText(
                        frame,
                        "Calculando geometria...",
                        (10, 40),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (0, 255, 255),
                        2,
                    )
                    centro_suavizado_x = 0
                    centro_suavizado_y = 0

            else:
                centro_suavizado_x = 0
                centro_suavizado_y = 0
                cv2.putText(
                    frame,
                    "BUSCANDO BOTELLA...",
                    (10, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (0, 0, 255),
                    2,
                )

            cv2.imshow("Alineacion Visual", frame)

            if cv2.waitKey(1) & 0xFF == 27:
                self._running = False
                break

        cap.release()
        cv2.destroyAllWindows()