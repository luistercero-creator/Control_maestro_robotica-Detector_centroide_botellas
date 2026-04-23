from dataclasses import dataclass


@dataclass(frozen=True)
class ControlDecision:
    axis: str
    command: str
    movement_mm: float
    reason: str


class ControlLogic:
    def __init__(self, config):
        self.cfg = config
        self.auto_mode = False
        self.manual_centroid_mode = False

    def reset(self) -> None:
        self.auto_mode = False
        self.manual_centroid_mode = False

    def is_centroid_enabled(self) -> bool:
        return self.auto_mode or self.manual_centroid_mode

    def toggle_auto_mode(self) -> bool:
        self.auto_mode = not self.auto_mode
        if self.auto_mode:
            self.manual_centroid_mode = True
        return self.auto_mode

    def set_auto_mode(self, enabled: bool) -> None:
        self.auto_mode = bool(enabled)
        if self.auto_mode:
            self.manual_centroid_mode = True

    def toggle_centroid_mode(self) -> bool:
        self.manual_centroid_mode = not self.manual_centroid_mode
        return self.manual_centroid_mode

    def set_centroid_mode(self, enabled: bool) -> None:
        self.manual_centroid_mode = bool(enabled)

    def decide(self, analysis, robot_busy: bool):
        if robot_busy:
            return None

        if not self.is_centroid_enabled():
            return None

        if not analysis.detected:
            return None

        if analysis.aligned:
            return None

        error_x = analysis.error_robot_x
        error_y = analysis.error_robot_y

        if abs(error_x) > self.cfg.center_tolerance_px:
            mm = round(error_x * self.cfg.mm_per_px, 1)
            return ControlDecision(
                axis="X",
                command=f"X,{-mm}",
                movement_mm=-mm,
                reason="Corrección prioritaria en eje X",
            )

        if abs(error_y) > self.cfg.center_tolerance_px:
            mm = round(error_y * self.cfg.mm_per_px, 1)
            return ControlDecision(
                axis="Y",
                command=f"Y,{-mm}",
                movement_mm=-mm,
                reason="Corrección secundaria en eje Y",
            )

        return None