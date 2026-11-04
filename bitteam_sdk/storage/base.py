from abc import ABC, abstractmethod
from typing import List
from ..models import Kline

class StorageBackend(ABC):
    @abstractmethod
    async def init(self): ...
    @abstractmethod
    async def save_kline(self, kline: Kline): ...
    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int) -> List[list]: ...