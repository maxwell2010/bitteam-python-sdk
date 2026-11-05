"""Candle storage contracts; rows preserve the supplied decimal strings.

Backends keep the latest 2000 rows per exact (symbol, interval) by default.
Pass retention=None for explicit full-history persistence. Rolling retention is
not a claim of a complete exchange archive. Initialize before use and close
owned resources after use; close is idempotent.
"""
from abc import ABC, abstractmethod
from typing import List
from ..models import Kline


def validate_retention(retention):
    if retention is not None and (isinstance(retention, bool) or not isinstance(retention, int) or retention < 1):
        raise ValueError("retention must be a positive integer or None")


def validate_limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")


class StorageBackend(ABC):
    @abstractmethod
    async def init(self): ...
    @abstractmethod
    async def save_kline(self, kline: Kline): ...
    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int) -> List[tuple]: ...

    async def close(self):
        """Release backend resources, when any are owned."""
