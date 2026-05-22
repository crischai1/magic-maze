"""Delta ops broadcast to clients to keep them in sync."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class DeltaOp:
    op: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = {"op": self.op}
        for k, v in self.__dict__.items():
            if k == "op":
                continue
            if hasattr(v, "value"):  # Enum
                d[k] = v.value
            elif isinstance(v, tuple):
                d[k] = list(v)
            else:
                d[k] = v
        return d


@dataclass
class MovePawnOp(DeltaOp):
    op: str = "move_pawn"
    color: Optional[str] = None
    from_pos: Optional[tuple[int, int]] = None
    to_pos: Optional[tuple[int, int]] = None


@dataclass
class FlipPawnOp(DeltaOp):
    op: str = "flip_pawn"
    color: Optional[str] = None
    has_item: bool = False


@dataclass
class PawnExitOp(DeltaOp):
    op: str = "pawn_exit"
    color: Optional[str] = None


@dataclass
class PhaseChangeOp(DeltaOp):
    op: str = "phase_change"
    new_phase: Optional[str] = None


@dataclass
class PlaceTileOp(DeltaOp):
    op: str = "place_tile"
    tile_id: str = ""
    origin: Optional[tuple[int, int]] = None
    rotation: int = 0
    # The door cell on the SOURCE (previous) tile that was walked through.
    explored_anchor: Optional[tuple[int, int]] = None
    # The door cell on the NEW (just-placed) tile that the hero entered.
    # Both doors should disappear once explored.
    entrance_anchor: Optional[tuple[int, int]] = None
    # Any ADDITIONAL doors sealed by _seal_doors_facing_placed_tiles() beyond
    # the primary two above. Must be sent so clients hide those arrows too.
    sealed_anchors: Optional[list] = None


@dataclass
class TimerFlipOp(DeltaOp):
    """Flips the sand timer (resets remaining time to its starting value)."""
    op: str = "timer_flip"


@dataclass
class OpenChatOp(DeltaOp):
    op: str = "open_chat"
    expires_at_ms: int = 0


@dataclass
class CloseChatOp(DeltaOp):
    op: str = "close_chat"


@dataclass
class EndGameOp(DeltaOp):
    op: str = "end_game"
    outcome: Optional[str] = None
    reason: str = ""


@dataclass
class UseSandTimerOp(DeltaOp):
    """Mark a Sand-Timer space (or Camera/Crystal-Ball) used; place an Out-of-Order marker."""
    op: str = "use_sand_timer"
    pos: Optional[tuple[int, int]] = None


@dataclass
class UseCrystalBallOp(DeltaOp):
    op: str = "use_crystal_ball"
    pos: Optional[tuple[int, int]] = None


@dataclass
class RequireExplorationOp(DeltaOp):
    op: str = "require_exploration"
    player_id: str = ""
    anchor_pos: Optional[tuple[int, int]] = None
    extra_tiles: int = 1  # 1 normally; 2 if Mage triggered via Crystal Ball


@dataclass
class ExplorationDoneOp(DeltaOp):
    op: str = "exploration_done"
    # Doors sealed when the adjacent slot was already occupied (no new tile placed).
    sealed_anchors: Optional[list] = None
