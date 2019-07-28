from .exc import *

from typing import Any, Union, Optional
from threading import Lock, RLock, Condition


class Promise(object):
    __value: Any
    __error: Exception

    def __init__(self, lock: Union[Lock, RLock, None] = None):
        self.__cv = Condition(lock)
        # 0 - promise не выполнен
        # 1 - promise выполнен
        # 2 - во время выполнения произошла ошибка
        self.__state = 0

    def set_result(self, value: Any) -> None:
        """
        Сохраняет в promise результат и оповещает о нем другие потоки.
        """
        with self.__cv:
            # Проверим, что promise уже не выполнен
            assert self.__state == 0
            # Сохраняем результат:
            self.__value = value
            # Отмечаем, что promise выполнен:
            self.__state = 1
            # Если другие потоки ждут результата, оповестим их:
            self.__cv.notify_all()

    def set_error(self, error: Exception) -> None:
        """
        Сохраняет в promise ошибку и оповещает о ней другие потоки.
        """
        with self.__cv:
            # Проверим, что promise уже не выполнен
            assert self.__state == 0
            # Сохраняем ошибку:
            self.__error = error
            # Отмечаем, что выполнение закончилось ошибкой
            self.__state = 2
            # Если другие потоки ждут результата, оповестим их:
            self.__cv.notify_all()

    def get(self, timeout: Optional[float] = None) -> Any:
        """
        Ждет, пока promise не будет выполнен, и возвращает результат.

        :param timeout: Максимальное время ожидания
        """
        if self.__state == 0:
            with self.__cv:
                # Если promise не выполнен, дождемся пока появится результат
                if not self.__cv.wait_for(lambda: self.__state != 0, timeout):
                    raise TimeoutException()
        # Если state != 1, значит, promise завершился с ошибкой
        if self.__state != 1:
            raise self.__error
        # Возвращаем результат
        return self.__value

    def cancel(self) -> None:
        self.set_error(CancelledException())

    @property
    def cancelled(self):
        return self.__state == 2 and isinstance(self.__error, CancelledException)

    @property
    def done(self):
        return self.__state != 0
