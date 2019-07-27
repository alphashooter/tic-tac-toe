from typing import Optional
from time import time


class Timer(object):
    def __init__(self, limit: Optional[float] = None):
        self.__time = time()
        self.limit = limit

    def reset(self) -> None:
        self.__time = time()

    @property
    def left(self) -> Optional[float]:
        if self.limit is None:
            return None
        return self.limit - self.passed

    @property
    def passed(self):
        return time() - self.__time

    @property
    def timed_out(self):
        left = self.left
        return left is not None and left < 0
