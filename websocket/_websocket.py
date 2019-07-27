from ._settings import *
from .exc import *

from typing import Optional, Union, Tuple, Deque, Dict, Callable
from collections import deque
from socket import socket, SHUT_WR
from select import select
from threading import Thread, RLock, Condition
from concurrent import Promise
from utility import Timer


def _parse_http(data: str):
    assert len(data) > 4 and data[-4:] == '\r\n\r\n', 'HTTP request is not terminated'
    lines = data[:-4].split('\r\n')
    method, uri, version = _parse_http_request(lines[0])
    headers = dict(map(_parse_http_header, lines[1:]))
    return method, uri, version, headers


def _parse_http_request(data: str):
    match = REQUEST_REGEX.match(data)
    assert match, 'Invalid HTTP request'
    return match.group(1), match.group(2), match.group(3)


def _parse_http_header(data: str):
    match = HEADER_REGEX.match(data)
    assert match, 'Invalid HTTP header'
    return match.group(1), match.group(2)


def _create_accept_key(key: str):
    import hashlib
    import base64
    key += '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    key = hashlib.new('sha1', key.encode()).digest()
    return base64.b64encode(key).decode()


class WebSocket(object):
    def __init__(self, client: socket):
        self.__client = client

        self.__input: Deque[Union[str, bytes]] = deque()
        self.__output: Deque[Tuple[Optional[Promise], int, bytes]] = deque()
        self.__ping: Dict[bytes, Promise] = {}

        self.__lock = RLock()
        self.__cv = Condition(self.__lock)

        self.__closed = False
        self.__reason = None
        self.__code = None

    def __del__(self):
        self.close()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self):
        return f'<WebSocket object at {hex(id(self))}>'

    def accept(self, timeout: Optional[float] = None, validate: Optional[Callable[[...], bool]] = None) -> None:
        response = None
        error = None

        try:
            client = self.__client
            client.setblocking(False)

            timer = Timer(timeout)
            data = b''

            while len(data) < 0x1000:
                left = timer.left
                if left is not None and left < 0:
                    raise RequestTimeout('Operation timed out')
                r, w, x = select([client], [], [], left)
                if self.__client not in r:
                    continue
                data = client.recv(0x1000 - len(data))
                if len(data) > 4 and data[-4:] == b'\r\n\r\n':
                    break

            try:
                method, uri, version, headers = _parse_http(data.decode())
            except Exception as exc:
                raise BadRequest(*exc.args)

            connection = headers.get('Connection', None)
            upgrade = headers.get('Upgrade', None)
            key = headers.get('Sec-WebSocket-Key', None)

            if method != 'GET':
                raise MethodNotAllowed(f'Expected method is GET, but got {method}')
            if version != '1.1':
                raise UpgradeRequired(f'Expected HTTP version is 1.1, but got {version}')
            if connection != 'Upgrade':
                raise UpgradeRequired(f'Expected Connection value is "Upgrade", but got "{connection}"')
            if upgrade != 'websocket':
                raise BadRequest(f'Expected Upgrade value is "websocket", but got "{upgrade}"')
            if key is None:
                raise BadRequest(f'Sec-WebSocket-Key is missed')
            if validate is not None and not validate(uri, headers):
                raise BadRequest(f'Validation failed')

            response = (
                f'HTTP/1.1 101 WebSocket Upgrade\r\n'
                f'Connection: Upgrade\r\n'
                f'Upgrade: websocket\r\n'
                f'Sec-WebSocket-Accept: {_create_accept_key(key)}\r\n'
                f'\r\n'
            )
        except BadRequest as exc:
            error = exc
            response = (
                f'HTTP/1.1 400 Bad Request\r\n'
                f'\r\n'
            )
        except MethodNotAllowed as exc:
            error = exc
            response = (
                f'HTTP/1.1 405 Method Not Allowed\r\n'
                f'\r\n'
            )
        except RequestTimeout as exc:
            error = exc
            response = (
                f'HTTP/1.1 408 Request Timeout\r\n'
                f'\r\n'
            )
        except UpgradeRequired as exc:
            error = exc
            response = (
                f'HTTP/1.1 426 Upgrade Required\r\n'
                f'Connection: Upgrade\r\n'
                f'Upgrade: websocket\r\n'
                f'\r\n'
            )
        except Exception as exc:
            error = exc

        if response:
            try:
                self.__client.sendall(response.encode())
            except Exception as exc:
                if not error:
                    error = exc

        if error:
            self.__close()
            raise error
        else:
            Thread(target=self.__run).start()

    def __send_all(self, data: Union[bytes, bytearray]) -> None:
        self.__client.sendall(data)

    def __recv_all(self, n: int) -> bytes:
        data = b''
        while len(data) < n:
            data += self.__client.recv(n - len(data))
        return data

    def __send_packet(self, opcode: int, data: Union[bytes, bytearray]) -> None:
        self.__client.setblocking(True)

        header = bytearray()
        header.append(0x80 | opcode)

        length = len(data)
        if length < 126:
            header.append(length)
        elif length < 0x10000:
            header.append(126)
            header.extend(length.to_bytes(2, 'big'))
        else:
            header.append(127)
            header.extend(length.to_bytes(8, 'big'))

        self.__send_all(header)
        self.__send_all(data)
        logger.debug(
            f'{self} sent {len(data)} bytes, '
            f'FIN=1, '
            f'OPCODE=0x{opcode:02x} ({OPCODE_NAME.get(opcode, "unknown")})'
        )

    def __recv_packet(self) -> Tuple[int, int, bytes]:
        self.__client.setblocking(True)

        octet, = self.__recv_all(1)
        fin = octet >> 7
        opcode = octet & 0x0F

        octet, = self.__recv_all(1)
        mask = octet >> 7
        length = octet & 0x7F

        if length == 126:
            length = int.from_bytes(self.__recv_all(2), 'big')
        elif length == 127:
            length = int.from_bytes(self.__recv_all(8), 'big')

        if mask:
            key = self.__recv_all(4)
        else:
            key = None

        data = self.__recv_all(length)
        if key:
            data = bytes(data[i] ^ key[i % 4] for i in range(len(data)))

        logger.debug(
            f'{self} received {len(data)} bytes, '
            f'FIN={fin}, '
            f'OPCODE=0x{opcode:02x} ({OPCODE_NAME.get(opcode, "unknown")})'
        )
        return fin, opcode, data

    def __send_message(self, opcode: int, data: Union[bytes, bytearray]) -> None:
        self.__send_packet(opcode, data)

    def __recv_message(self) -> Tuple[int, bytes]:
        fin, opcode, data = self.__recv_packet()

        result_opcode = opcode
        result_data = data
        while not fin:
            fin, opcode, data = self.__recv_packet()
            assert opcode == 0
            result_data += data
        return result_opcode, result_data

    def __run(self):
        while True:
            with self.__lock:
                if self.__closed:
                    break

            r, w, x = select([self.__client], [self.__client], [], 0.05)

            with self.__lock:
                if len(self.__output) and self.__client in w:
                    try:
                        while len(self.__output):
                            promise, opcode, data = self.__output.popleft()
                            if not promise or not promise.cancelled:
                                self.__send_message(opcode, data)
                            if promise:
                                promise.set_result(None)
                    except Exception as exc:
                        logger.error(f'{self} send error', exc_info=exc)
                        self.__close()
                        continue

                if self.__client in r:
                    try:
                        opcode, data = self.__recv_message()
                    except Exception as exc:
                        logger.error(f'{self} recv error', exc_info=exc)
                        self.__close(REASON_PROTOCOL_ERROR)
                        continue

                    if opcode == OPCODE_PING:
                        self.__output.append((None, OPCODE_PONG, data))
                    elif opcode == OPCODE_PONG:
                        promise = self.__ping.pop(data, None)
                        if promise:
                            promise.set_result(None)
                    elif opcode == OPCODE_CLOSE:
                        self.__code = int.from_bytes(data[:2], 'big')
                        self.__reason = data.decode(errors='ignore')
                        self.__close()
                    elif opcode == OPCODE_BINARY:
                        self.__input.append(data)
                        self.__cv.notify_all()
                    elif opcode == OPCODE_TEXT:
                        self.__input.append(data.decode(errors='ignore'))
                        self.__cv.notify_all()
                    else:
                        self.__close(REASON_NOT_SUPPORTED)

    def __close(self, reason: Optional[int] = None) -> None:
        with self.__lock:
            if self.__closed:
                return

            if reason:
                message = REASON_MESSAGE.get(reason, '')
                self.__code = reason
                self.__message = message
                try:
                    self.__send_message(OPCODE_CLOSE, reason.to_bytes(2, 'big') + message.encode())
                except Exception as exc:
                    logger.warning(f'{self} close error', exc_info=exc)
                    pass

            try:
                self.__client.shutdown(SHUT_WR)
            except Exception as exc:
                logger.warning(f'{self} shutdown error', exc_info=exc)

            self.__client.close()
            self.__closed = True

            self.__cv.notify_all()

    def send(self, data: Union[str, bytes, bytearray], timeout: Optional[float] = None) -> None:
        with self.__lock:
            if self.__closed:
                raise IOError('WebSocket is closed')

            promise = Promise(self.__lock)
            if isinstance(data, str):
                opcode = OPCODE_TEXT
                data = data.encode()
            else:
                opcode = OPCODE_BINARY

            self.__output.append((promise, opcode, data))
            try:
                promise.get(timeout)
            except TimeoutError:
                promise.cancel()

    def recv(self, timeout: Optional[float] = None) -> Union[str, bytes]:
        with self.__lock:
            if not self.__cv.wait_for(lambda: self.__closed or len(self.__input), timeout):
                raise TimeoutError('Operation timed out')
            if self.__input:
                return self.__input.popleft()
            raise IOError('WebSocket is closed')

    def ping(self, timeout: float) -> bool:
        from random import randint

        with self.__lock:
            if self.__closed:
                raise IOError('WebSocket is closed')

            promise = Promise(self.__lock)
            data = bytes(randint(0, 255) for i in range(4))
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
        self.__close(REASON_NORMAL)

    @property
    def closed(self):
        return self.__closed

    @property
    def code(self):
        return self.__code

    @property
    def reason(self):
        return self.__reason
