"""Sand timer that ticks down in real time. Pausable, supports time bonuses."""
from __future__ import annotations


class SandTimer:
    def __init__(self, starting_ms: int):
        self.starting_ms = starting_ms
        self.remaining_ms = starting_ms
        self.paused = False

    def tick(self, elapsed_ms: int) -> None:
        if self.paused:
            return
        self.remaining_ms = max(0, self.remaining_ms - elapsed_ms)

    def add_bonus(self, ms: int) -> None:
        self.remaining_ms = min(self.starting_ms, self.remaining_ms + ms)

    def reset(self) -> None:
        self.remaining_ms = self.starting_ms

    def flip(self) -> None:
        """Flip the physical sand timer: the sand below is now above.
        If X ms have already elapsed, X ms is now the new remaining time
        (and starting_ms - X ms has 'fallen through'). Per the rulebook
        this can give you more or less time depending on when you flip.
        """
        elapsed = self.starting_ms - self.remaining_ms
        self.remaining_ms = elapsed

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    @property
    def expired(self) -> bool:
        return self.remaining_ms <= 0
