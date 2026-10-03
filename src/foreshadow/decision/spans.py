"""Measured calendar spans. Missing days never become samples."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class MeasuredPoint:
    on: date
    value: int


@dataclass(frozen=True)
class ObservationSpan:
    points: tuple[MeasuredPoint, ...]

    @classmethod
    def normalize(cls, series: list[dict], *, key: str) -> ObservationSpan:
        points = []
        seen = set()
        for item in series:
            if item.get(key) is None:
                continue
            on = date.fromisoformat(str(item["date"]))
            if on in seen:
                raise ValueError("duplicate observation date")
            seen.add(on)
            value = item[key]
            if type(value) is not int:
                raise ValueError("measurement must be an integer")
            points.append(MeasuredPoint(on, value))
        return cls(tuple(sorted(points, key=lambda item: item.on)))

    @property
    def calendar_days(self) -> int:
        if not self.points:
            return 0
        return (self.points[-1].on - self.points[0].on).days + 1

    def exactly_covers(self, days: int) -> bool:
        return len(self.points) == days and self.calendar_days == days
