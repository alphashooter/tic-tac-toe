from .exc import *

from typing import Generic, TypeVar, Union, Optional
from threading import Lock, RLock, Condition


T = TypeVar('T')


class Promise(Generic[T]):
    __value: T
    __error: Exception

    def __init__(self, lock: Union[Lock, RLock, None] = None):
        self.__cv = Condition(lock)
        self.__state = 0

    def set_result(self, value: T) -> None:
        with self.__cv:
            assert self.__state == 0
            self.__value = value
            self.__state = 1
            self.__cv.notify_all()

    def set_error(self, error: Exception) -> None:
        with self.__cv:
            assert self.__state == 0
            self.__error = error
            self.__state = 2
            self.__cv.notify_all()

    def get(self, timeout: Optional[float] = None) -> T:
        if self.__state == 0:
            with self.__cv:
                if not self.__cv.wait_for(lambda: self.__state != 0, timeout):
                    raise TimeoutException()
        if self.__state != 1:
            raise self.__error
        return self.__value

    def cancel(self) -> None:
        self.set_error(CancelledException())

    @property
    def cancelled(self):
        return self.__state == 2 and isinstance(self.__error, CancelledException)

    @property
    def done(self):
        return self.__state != 0
