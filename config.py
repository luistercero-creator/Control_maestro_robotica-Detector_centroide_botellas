from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    # Red y robot
    robot_ip: str = "192.168.1.21"
    robot_port: int = 8000

    # Proyecto IA
    project_path: str = "converted_keras"
    camera_index: int = 1

    # Visión artificial
    confidence_threshold: float = 0.90
    center_tolerance_px: int = 30
    smoothing_factor: float = 0.2
    mm_per_px: float = 0.05

    # Calibración física
    camera_rotated_90: bool = True
    robot_x_inverter: int = 1
    robot_y_inverter: int = 1

    # Cámara
    use_dshow: bool = True


APP_CONFIG = AppConfig()