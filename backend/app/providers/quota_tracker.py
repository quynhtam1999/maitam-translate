"""Đếm quota CỤC BỘ theo cửa sổ trượt (A6b).

Google/Alibaba không trả 'quota còn lại' qua API, nên ta tự đếm: mỗi lần gọi thật
ghi lại (thời điểm, token vào, token ra); RPM/TPM tính theo cửa sổ trượt 60s, RPD
tính theo ngày với mốc reset lệch UTC theo từng provider.

Bản scaffold lưu trong bộ nhớ tiến trình. TODO: nếu chạy nhiều worker, chuyển sang
bảng SQLite quota_events(provider, ts, tokens_in, tokens_out) để đếm chung chính xác.
"""
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from ..models.provider import QuotaSnapshot

# Lệch UTC cho mốc reset RPD hằng ngày (A6b): Google ~ giờ Thái Bình Dương (-8),
# ModelScope ~ giờ Bắc Kinh (+8). Có thể lệch ±1h quanh đợt đổi giờ — đủ để cảnh báo sớm.
PROVIDER_UTC_OFFSET_HOURS = {
    "gemini": -8,
    "gemma": -8,
    "qwen": 8,
}


class _Event:
    __slots__ = ("ts", "tokens")

    def __init__(self, ts: float, tokens: int):
        self.ts = ts
        self.tokens = tokens


class QuotaTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # cửa sổ trượt 60s: hàng đợi sự kiện gọi cho từng provider
        self._events: dict[str, deque[_Event]] = defaultdict(deque)
        # đếm theo ngày: (provider) -> (ngày_reset_iso, requests, tokens)
        self._daily: dict[str, dict] = defaultdict(lambda: {"day": None, "requests": 0, "tokens": 0})

    def record(
        self,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        scope: str | None = None,
    ) -> None:
        bucket = self._bucket(provider, scope)
        now = time.time()
        total = tokens_in + tokens_out
        with self._lock:
            self._events[bucket].append(_Event(now, total))
            self._prune(bucket, now)

            day = self._current_reset_day(provider)
            d = self._daily[bucket]
            if d["day"] != day:
                d["day"], d["requests"], d["tokens"] = day, 0, 0
            d["requests"] += 1
            d["tokens"] += total

    def snapshot(
        self,
        provider: str,
        rpm_limit: int,
        tpm_limit: int,
        rpd_limit: int,
        scope: str | None = None,
    ) -> QuotaSnapshot:
        bucket = self._bucket(provider, scope)
        now = time.time()
        with self._lock:
            self._prune(bucket, now)
            events = self._events[bucket]
            rpm_used = len(events)
            tpm_used = sum(e.tokens for e in events)
            d = self._daily[bucket]
            day = self._current_reset_day(provider)
            rpd_used = d["requests"] if d["day"] == day else 0

        return QuotaSnapshot(
            provider=provider,
            rpm_used=rpm_used,
            rpm_limit=rpm_limit,
            tpm_used=tpm_used,
            tpm_limit=tpm_limit,
            rpd_used=rpd_used,
            rpd_limit=rpd_limit,
            resets_at=self._next_reset_iso(provider),
        )

    def wait_seconds_until_ready(
        self,
        provider: str,
        rpm_limit: int,
        tpm_limit: int,
        rpd_limit: int,
        estimated_tokens: int = 0,
        scope: str | None = None,
    ) -> float | None:
        """Return seconds to wait for minute limits, 0 if ready, None if RPD is exhausted."""
        bucket = self._bucket(provider, scope)
        now = time.time()
        with self._lock:
            self._prune(bucket, now)
            if rpd_limit > 0 and self._daily_requests_locked(provider, bucket) >= rpd_limit:
                return None

            events = self._events[bucket]
            waits: list[float] = []

            if rpm_limit > 0 and len(events) >= rpm_limit:
                waits.append(self._seconds_until_event_expires(events[0], now))

            token_need = max(0, int(estimated_tokens or 0))
            if tpm_limit > 0 and events:
                tpm_used = sum(e.tokens for e in events)
                if token_need >= tpm_limit:
                    needed_to_free = tpm_used
                else:
                    needed_to_free = tpm_used + token_need - tpm_limit

                if needed_to_free > 0:
                    freed = 0
                    for event in events:
                        freed += event.tokens
                        if freed >= needed_to_free:
                            waits.append(self._seconds_until_event_expires(event, now))
                            break

            return max(waits, default=0.0)

    # --- helpers ---
    def _prune(self, bucket: str, now: float) -> None:
        q = self._events[bucket]
        while q and now - q[0].ts > 60:
            q.popleft()

    def _daily_requests_locked(self, provider: str, bucket: str) -> int:
        d = self._daily[bucket]
        day = self._current_reset_day(provider)
        return d["requests"] if d["day"] == day else 0

    @staticmethod
    def _bucket(provider: str, scope: str | None) -> str:
        return f"{scope}:{provider}" if scope else provider

    @staticmethod
    def _seconds_until_event_expires(event: _Event, now: float) -> float:
        return max(0.0, 60.0 - (now - event.ts) + 0.25)

    def _current_reset_day(self, provider: str) -> str:
        offset = PROVIDER_UTC_OFFSET_HOURS.get(provider, 0)
        local = datetime.now(timezone.utc) + timedelta(hours=offset)
        return local.date().isoformat()

    def _next_reset_iso(self, provider: str) -> str:
        offset = PROVIDER_UTC_OFFSET_HOURS.get(provider, 0)
        tz = timezone(timedelta(hours=offset))
        local = datetime.now(tz)
        next_midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return next_midnight.astimezone(timezone.utc).isoformat()


# Singleton dùng chung toàn app
quota_tracker = QuotaTracker()
