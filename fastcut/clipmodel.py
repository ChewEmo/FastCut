from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Clip:
    pos: int
    start: int
    end: int

    @property
    def length(self) -> int:
        return max(0, self.end - self.start)

    @property
    def out_pos(self) -> int:
        return self.pos + self.length

    def copy(self) -> "Clip":
        return Clip(self.pos, self.start, self.end)

    def as_tuple(self) -> tuple[int, int, int]:
        return (self.pos, self.start, self.end)

    @staticmethod
    def from_tuple(t) -> "Clip":
        return Clip(int(t[0]), int(t[1]), int(t[2]))
