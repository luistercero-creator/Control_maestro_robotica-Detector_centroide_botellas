from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    # Red
    robot_ip: str = "192.168.125.1"
    robot_port: int = 8000

    # IA
    model_path: str = "converted_keras/keras_model.h5"
    labels_path: str = "converted_keras/labels.txt"

    # Cámara
    camera_index: int = 0
    use_dshow: bool = True

    # Visión
    confidence_threshold: float = 0.90
    center_tolerance_px: int = 30
    smoothing_factor: float = 0.20
    mm_per_px: float = 0.05

    # Calibración
    camera_rotated_90: bool = True
    invert_robot_x: int = 1
    invert_robot_y: int = 1


CONFIG = AppConfig()