# src/llm/rate_limiter.py
import asyncio
from collections import deque
from datetime import datetime, timedelta
from typing import Deque

class RateLimiter:
    """
    RPM/RPD の両面で制御する簡易レートリミッタ（トークンバケット風）。
    """
    def __init__(self, rpm: int, rpd: int):
        self.rpm = max(1, int(rpm))
        self.rpd = max(1, int(rpd))
        self._per_minute: Deque[datetime] = deque()
        self._per_day: Deque[datetime] = deque()

    async def acquire(self):
        while True:
            now = datetime.utcnow()
            # 窓外を掃除
            one_min = now - timedelta(minutes=1)
            one_day = now - timedelta(days=1)
            while self._per_minute and self._per_minute[0] <= one_min:
                self._per_minute.popleft()
            while self._per_day and self._per_day[0] <= one_day:
                self._per_day.popleft()

            if len(self._per_minute) < self.rpm and len(self._per_day) < self.rpd:
                self._per_minute.append(now)
                self._per_day.append(now)
                return
            # 次のスロットまで待機（短い方）
            sleep_min = (self._per_minute[0] - one_min).total_seconds() if self._per_minute else 0.5
            sleep_day = (self._per_day[0] - one_day).total_seconds() if self._per_day else 0.5
            await asyncio.sleep(max(0.5, min(sleep_min, sleep_day)))
