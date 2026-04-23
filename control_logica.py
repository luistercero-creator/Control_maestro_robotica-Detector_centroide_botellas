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

    def decide(self, analysis, robot_busy: bool) -> ControlDecision | None:
        if robot_busy:
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