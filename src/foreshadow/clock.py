from datetime import UTC, date, datetime


class Clock:
    """Injectable UTC clock. Pass ``now=`` to freeze time in tests."""

    def __init__(self, now: datetime | None = None) -> None:
        if now is not None and now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        self._now = now

    def now(self) -> datetime:
        if self._now is not None:
            return self._now
        return datetime.now(UTC)

    def today(self) -> date:
        return self.now().astimezone(UTC).date()
