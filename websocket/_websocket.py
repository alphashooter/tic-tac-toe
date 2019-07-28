from ._settings import *

from typing import Optional, Union, Tuple, Deque, Dict, Callable
from collections import deque
from socket import socket, SHUT_WR
from select import select
from threading import Thread, RLock, Condition
from concurrent import Promise


class WebSocket(object):
    def __init__(self, client: socket):
        self.__client = client

        self.__input: Deque[Union[str, bytes]] = deque()
        self.__output: Deque[Tuple[Optional[Promise], int, bytes]] = deque()
        self.__ping: Dict[bytes, Promise] = {}

        self.__thread: Optional[Thread] = None
        self.__lock = RLock()
        self.__cv = Condition(self.__lock)

        self.__handshake = False
        self.__closed = False
        self.__reason = None
        self.__code = None

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self):
        return f'<WebSocket object at {hex(id(self))}>'

    def accept(self, timeout: Optional[float] = None, validate: Optional[Callable[[str], bool]] = None) -> None:
        """
        Устанавливает WebSocket соединение в роли сервера.

        Параметры имеют то же значение, что и в websocket._accept.accept.

        :param timeout: Максимальное время на установку соединения
        :param validate: Функция для проверки URI запроса
        :return:
        """
        from ._accept import accept

        # Перед началом установки соединения захватываем мьютекс,
        # чтобы избежать одновременных accept/close
        with self.__lock:
            # Перед accept, мы должны проверить, что сокет не закрыт (closed),
            # и что мы уже не установили с ним соединение (handshake)
            assert not self.__closed
            assert not self.__handshake

            # Логика accept вынесена в отдельный модуль
            accept(self.__client, timeout, validate)

            # Если во время accept не произошло ошибки,
            # то ставим handshake в True, чтобы accept нельзя было вызвать еще раз
            self.__handshake = True

            # Запускаем фоновый поток чтения/записи в сокет
            self.__thread = Thread(target=self.__run)
            self.__thread.start()

    def __send_all(self, data: Union[bytes, bytearray]) -> None:
        """
        Отправляет data в сокет *полностью* - socket.send() не гарантирует, что
        отправит все переданные ему данные. Эта функция гарантирует, что
        все данные будут отправлены.

        :param data: Данные для отправки в сокет
        """
        self.__client.sendall(data)

    def __recv_all(self, n: int) -> bytes:
        """
        Считывает *ровно* ``n`` байт из сокета - socket.recv() не гарантирует, что
        считает ровно n байт. Эта функция гарантирует, что все данные будут считаны.

        :param n: Количество байт, которое необходимо считать из сокета.
        :return: Считанные данные
        """
        data = b''
        while len(data) < n:
            data += self.__client.recv(n - len(data))
        return data

    def __send_packet(self, opcode: int, data: Union[bytes, bytearray]) -> None:
        """
        Отправляет *один* пакет в сокет. Эта функция необходима для поддержки фрагментации сообщений.

        :param opcode: opcode пакета
        :param data: данные пакета
        """
        self.__client.setblocking(True)

        header = bytearray()
        # Записываем FIN = 1, RSV1-3 = 0 (0x80) и OPCODE в первый байт пакета
        header.append(0x80 | opcode)

        length = len(data)
        if length < 126:
            # Если длина пакета меньше 126, то в следующий байт записываем длину
            header.append(length)
        elif length < 0x10000:
            # Если длина пакета меньше 0x10000, то в следующий байт записываем 126, а затем 2 байта длины
            header.append(126)
            header.extend(length.to_bytes(2, 'big'))
        else:
            # Если длина пакета больше 0x10000, то в следующий байт записываем 127, а затем 8 байт длины
            header.append(127)
            header.extend(length.to_bytes(8, 'big'))

        # Отправляем заголовок пакета (FIN=1, RSV1-3=0, OPCODE, MASK=0, LENGTH)
        self.__send_all(header)
        # Отправляем сами данные
        self.__send_all(data)
        logger.debug(
            f'{self} sent {len(data)} bytes, '
            f'FIN=1, '
            f'OPCODE=0x{opcode:02x} ({OPCODE_NAME.get(opcode, "unknown")})'
        )

    def __recv_packet(self) -> Tuple[int, int, bytes]:
        """
        Принимает *один* пакет из сокета. Эта функция необходима для поддержки фрагментации сообщений.

        :return: Значения fin, opcode и data принятого пакета
        """
        self.__client.setblocking(True)

        # Считываем первый байт пакета
        octet, = self.__recv_all(1)
        # Вычисляем значение FIN (8-ой бит)
        fin = octet >> 7
        # Вычисляем значение OPCODE (1-4 биты)
        opcode = octet & 0x0F

        # Считываем второй байт пакета
        octet, = self.__recv_all(1)
        # Вычисляем значение MASK (8-ой бит)
        mask = octet >> 7
        # Вычисляем значение LENGTH (1-7 биты)
        length = octet & 0x7F

        if length == 126:
            # Если LENGTH = 126, то реальная длина записана в следующих двух байтах
            length = int.from_bytes(self.__recv_all(2), 'big')
        elif length == 127:
            # Если LENGTH = 127, то реальная длина записана в следующих восьми байтах
            length = int.from_bytes(self.__recv_all(8), 'big')

        if mask:
            # Если значение бита MASK пакета было 1, то после длины идет 4 байта ключа маски
            key = self.__recv_all(4)
        else:
            key = None

        data = self.__recv_all(length)
        if key:
            # Если данные маскированы, то для того, чтобы их восстановить, необходимо выполнить XOR с ключом маски
            data = bytes(data[i] ^ key[i % 4] for i in range(len(data)))

        logger.debug(
            f'{self} received {len(data)} bytes, '
            f'FIN={fin}, '
            f'OPCODE=0x{opcode:02x} ({OPCODE_NAME.get(opcode, "unknown")})'
        )
        return fin, opcode, data

    def __send_message(self, opcode: int, data: Union[bytes, bytearray]) -> None:
        """
        Отправляет сообщение в сокет. Сообщение может быть разбито на несколько пакетов (см. __send_packet()).

        :param opcode: opcode сообщения
        :param data: данные сообщения
        """
        self.__send_packet(opcode, data)

    def __recv_message(self) -> Tuple[int, bytes]:
        """
        Принимает сообщение из сокета. Сообщение может быть разбито на несколько пакетов (см. __recv_packet())
        :return: opcode и data принятого сообщения
        """
        fin, opcode, data = self.__recv_packet()

        result_opcode = opcode
        result_data = data

        # Если FIN пакета 0, то он фрагментирован, и нам необходимо склеивать его со следующими пакетами,
        # пока FIN не будет равен 1
        while not fin:
            fin, opcode, data = self.__recv_packet()
            # У фрагментированных пакетов OPCODE всегда должен быть 0
            assert opcode == 0
            # Добавляем данные пакета к предыдущим
            result_data += data

        # Возвращаем OPCODE из первого пакета и склеенные данные:
        return result_opcode, result_data

    def __run(self):
        """
        Цикл чтения/записи в сокет.
        """
        while True:
            with self.__lock:
                # В начале каждой итерации проверяем, что сокет не закрыт.
                # Если сокет закрыт, то выполнение потока можно прервать.
                if self.__closed:
                    break

            # Проверяем, можем ли мы выполнить чтение или запись
            r, w, x = select([self.__client], [self.__client], [], 0.05)

            with self.__lock:
                # Если в очереди на запись (output) есть сообщения, и сокет может выполнить запись,
                # то отправим все сообщения из очереди в сокет
                if len(self.__output) and self.__client in w:
                    try:
                        while len(self.__output):
                            # Берем следующее сообщение из очереди:
                            promise, opcode, data = self.__output.popleft()
                            # Проверяем, что отправку не отменили (promise.cancelled), пока сообщение было в очереди:
                            if not promise or not promise.cancelled:
                                # Отправляем сообщение:
                                self.__send_message(opcode, data)
                            # Если у сообщения есть promise, то оповещаем его, что мы выполнили отправку
                            if promise:
                                try:
                                    promise.set_result(None)
                                except Exception as exc:
                                    # У promise мог быть вызван cancel, пока мы отправляли сообщение.
                                    # Ничего страшного в этом нет, но на всякий случай запишем сообщение в лог. :)
                                    logger.debug(f'{self} failed to fulfill a promise', exc_info=exc)
                                    pass
                    except Exception as exc:
                        # Если во время записи произогла неведомая ошибка, то разорвем сооединение,
                        # потому что вероятнее всего работать дальше с этим сокетом будет невозможно.
                        logger.error(f'{self} send error', exc_info=exc)
                        self.__close()
                        continue

                # Если в сокете есть какие-то данные, то считаем сообщение и поместим в очередь на чтение (input)
                if self.__client in r:
                    try:
                        # Считываем сообщение
                        opcode, data = self.__recv_message()
                    except Exception as exc:
                        # Если во время чтения произошла ошибка, то вероятнее всего нам прислали что-то,
                        # чего мы не ожидали, поэтому отправим второй стороне ошибку протокола и закроем соединение.
                        logger.error(f'{self} recv error', exc_info=exc)
                        self.__close(REASON_PROTOCOL_ERROR)
                        continue

                    # Если сообщение, которое нам пришло, - это PING, то отправим в ответ PONG
                    if opcode == OPCODE_PING:
                        self.__output.append((None, OPCODE_PONG, data))
                    # Если сообщение, которое нам пришло, - это PONG,
                    # то найдем соответстующий ему promise и оповестим его, что все ОК.
                    elif opcode == OPCODE_PONG:
                        promise = self.__ping.pop(data, None)
                        if promise:
                            promise.set_result(None)
                    # Если нам пришло сообщение о закрытии соединения, то отправим SHUT_WR и закроем сокет.
                    elif opcode == OPCODE_CLOSE:
                        self.__code = int.from_bytes(data[:2], 'big')
                        self.__reason = data.decode(errors='ignore')
                        self.__close()
                    # Если нам пришли бинарные данные, то отправим их в очередь на чтение
                    elif opcode == OPCODE_BINARY:
                        self.__input.append(data)
                        # Если другие потоки ждут, пока в очередь придут данные, то нам нужно оповестить их
                        self.__cv.notify_all()
                    # Если нам пришли текстовые данные, то попробуем их декодировать и отправим в очередь на чтение
                    elif opcode == OPCODE_TEXT:
                        self.__input.append(data.decode(errors='ignore'))
                        # Если другие потоки ждут, пока в очередь придут данные, то нам нужно оповестить их
                        self.__cv.notify_all()
                    # Если нам пришел неизвестный OPCODE, то отправим ошибку и закроем сокет.
                    else:
                        self.__close(REASON_NOT_SUPPORTED)

    def __close(self, reason: Optional[int] = None) -> None:
        """
        Закрывает соединение.

        Если указан reason, то перед закрытием в сокет будет отправлено сообщение с указанием причины закрытия.

        :param reason: Код закрытия соединения
        :return:
        """
        with self.__lock:
            # Проверим, что сокет уже не закрыт
            if self.__closed:
                return

            # Если указана причина закрытия (reason) и соединение вообще установлено (handshake),
            # то попробуем отправить сообщение о закрытии:
            if self.__handshake and reason is not None:
                message = REASON_MESSAGE.get(reason, '')
                self.__code = reason
                self.__message = message
                try:
                    self.__send_message(OPCODE_CLOSE, reason.to_bytes(2, 'big') + message.encode())
                except Exception as exc:
                    logger.warning(f'{self} close error', exc_info=exc)
                    pass

            try:
                # Отправим shutdown, чтобы вторая сторона знала, что мы обрываем соединение:
                self.__client.shutdown(SHUT_WR)
            except Exception as exc:
                logger.warning(f'{self} shutdown error', exc_info=exc)

            # закроем сокет
            self.__client.close()
            self.__closed = True

            # В то время, когда мы закрывали сокет, в очереди на отправку могли быть сообщения.
            # Если такие сообщения есть, то оповестим ожидающие потоки, что сообщение не может быть отправлено.
            while len(self.__output):
                promise, opcode, data = self.__output.popleft()
                if promise and not promise.cancelled:
                    promise.set_error(IOError('WebSocket is closed'))

            # Помимо потоков, которые стояли в очереди на отправку, могут быть и те, кто ждет сообщения
            # в очереди на чтение, так что оповестим и их:
            self.__cv.notify_all()

    def send(self, data: Union[str, bytes, bytearray], timeout: Optional[float] = None) -> None:
        """
        Помещает сообщение в очередь на отправку.

        :param data: Сообщение
        :param timeout: Максимальное время на отправку
        """
        with self.__lock:
            # Проверим, что сокет не закрыт:
            if self.__closed:
                raise IOError('WebSocket is closed')

            # Создадим promise, чтобы поток чтения/записи мог нас оповестить об отправке:
            promise = Promise(self.__lock)

            # Подготавливаем сообщение:
            if isinstance(data, str):
                opcode = OPCODE_TEXT
                data = data.encode()
            else:
                opcode = OPCODE_BINARY

            # Помещаем сообщение в очередь:
            self.__output.append((promise, opcode, data))

            # Ждем, пока поток чтения/записи не оповестит нас об отправке:
            try:
                promise.get(timeout)
            except TimeoutError:
                promise.cancel()

    def recv(self, timeout: Optional[float] = None) -> Union[str, bytes]:
        """
        Извлекает сообщение из очереди на чтение.

        :param timeout: Максимальное время ожидания
        """
        with self.__lock:
            # Ждем пока в очереди не появятся сообщение или пока сокет не будет закрыт.
            if not self.__cv.wait_for(lambda: self.__closed or len(self.__input), timeout):
                # Если время ожидания истекло, выбросим ошибку:
                raise TimeoutError('Operation timed out')
            # Если в очереди есть сообщение, вернем его:
            if self.__input:
                return self.__input.popleft()
            # Если в очереди сообщений нет, значит сокет закрыт:
            raise IOError('WebSocket is closed')

    def ping(self, timeout: float) -> bool:
        """
        Отправляет второй стороне PING и в течение ``timeout`` ждет от него PONG.

        :param timeout: Время ожидания PONG
        :return: True если PONG пришел в течение timeout, иначе False
        """
        from random import randint

        with self.__lock:
            # Проверим, что сокет не закрыт:
            if self.__closed:
                raise IOError('WebSocket is closed')

            # Создадим promise, чтобы поток чтения/записи мог нас оповестить о том, что пришел PONG
            promise = Promise(self.__lock)

            # В качестве данных, которые мы передадим с PING, возьмем четыре случайных байта:
            data = bytes(randint(0, 255) for i in range(4))

            # Когда от второй стороны придет PONG, там должны быть те же самые четыре байта.
            # По ним поток чтения/записи сможет определить, к какому promise относился PONG.
            self.__ping[data] = promise
            self.__output.append((None, OPCODE_PING, data))

            try:
                promise.get(timeout)
            except Exception as exc:
                logger.debug(f'{self} ping error', exc_info=exc)
                del self.__ping[data]
                return False
            else:
                return True

    def close(self) -> None:
        """
        Закрывает сокет.
        """
        if self.__closed:
            return
        self.__close(REASON_NORMAL)
        if self.__thread and self.__thread.is_alive():
            self.__thread.join()
        self.__thread = None

    @property
    def closed(self):
        return self.__closed

    @property
    def code(self):
        return self.__code

    @property
    def reason(self):
        return self.__reason
