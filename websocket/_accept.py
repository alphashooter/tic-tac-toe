from typing import Optional, Callable
from socket import socket
from select import select
from utility import Timer
from .exc import *


# HTTP-ответы для некоторых типов ошибок:
BAD_REQUEST = 'HTTP/1.1 400 Bad Request\r\n\r\n'
NOT_FOUND = 'HTTP/1.1 404 Not Found\r\n\r\n'
METHOD_NOT_ALLOWED = 'HTTP/1.1 405 Method Not Allowed\r\n\r\n'
REQUEST_TIMEOUT = 'HTTP/1.1 408 Request Timeout\r\n\r\n'
UPGRADE_REQUIRED = (
    'HTTP/1.1 426 Upgrade Required\r\n'
    'Connection: Upgrade\r\n'
    'Upgrade: websocket\r\n'
    '\r\n'
)


def create_accept_key(key: str):
    """
    Вычисляет значение Sec-WebSocket-Accept из соответствующего Sec-WebSocket-Key.

    :param key: Значение Sec-WebSocket-Key
    :return: Значение Sec-WebSocket-Accept
    """
    import hashlib
    import base64
    # Sec-WebSocket-Accept формируется следующим образом:
    # base64(sha1(key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'))
    # где key - это значение Sec-WebSocket-Key в запросе клиента
    key += '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    key = hashlib.new('sha1', key.encode()).digest()
    return base64.b64encode(key).decode()


def create_response(request: str, validate: Optional[Callable[[str], bool]] = None) -> str:
    """
    Проверяет HTTP-запрос на установление WebSocket-соединения и возвращает соответствующий HTTP-ответ.

    Если передана функция ``validate``, то помимо проверки метода и заголовков запроса выполняется проверка:
    ::
        validate(uri) == True

    :param request: текст HTTP-запроса
    :param validate: Функция для проверки URI запроса
    :return: текст HTTP-ответа
    """
    from ._http import parse_http

    try:
        # Достаем из полученного запроса метод, URI, версию HTTP и заголовки:
        method, uri, version, headers = parse_http(request)
    except Exception as exc:
        # Если произошла какая-то ошибка, значит запрос сформирован неправильно,
        # поэтому выбрасываем ошибку BadRequest:
        raise BadRequest(*exc.args)

    # Достаем заголовки Connection, Upgrade и Sec-WebSocket-Key (они обязательно должны присутствовать в запросе):
    connection = headers.get('Connection', None)
    upgrade = headers.get('Upgrade', None)
    key = headers.get('Sec-WebSocket-Key', None)

    # Запрос должен иметь вид:
    #
    # GET {uri} HTTP/1.1\r\n
    # Connection: Upgrade\r\n
    # Upgrade: websocket\r\n
    # Sec-WebSocket-Key: {key}\r\n
    # \r\n
    #
    # Если:
    # 1. метод отличается от GET или версия HTTP от 1.1
    # 2. один из заголовков отсутствует или имеет неправильное значение
    # значит, запос сформирован неправильно.
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

    # Помимо этого, если была передана функция validate,
    # передадим туда URI и остальные заголовки запроса,
    # чтобы проверить и их
    if validate is not None and not validate(uri):
        raise NotFound(f'URI validation failed')

    return (
        f'HTTP/1.1 101 WebSocket Upgrade\r\n'
        f'Connection: Upgrade\r\n'
        f'Upgrade: websocket\r\n'
        f'Sec-WebSocket-Accept: {create_accept_key(key)}\r\n'
        f'\r\n'
    )


def accept(client: socket, timeout: Optional[float] = None, validate: Optional[Callable[[str], bool]] = None) -> None:
    """
    Считывает HTTP-запрос из сокета, проверяет его и отправляет соответствующий HTTP-ответ.

    Если в ``timeout`` передан ``float``, то время на получение запроса будет
    ограничено на соответствующее количество секунд. Если ``timeout = None``, то
    ограничения по времени не будет.

    ``validate`` имеет то же значение, что и в create_response.

    :param client: Сокет, с которым мы хотим установить соединение.
    :param timeout: Максимальное время на установку соединения.
    :param validate: Функция для проверки URI запроса.
    """

    response = None
    error = None
    try:
        client.setblocking(False)
        timer = Timer(timeout)
        data = b''

        # Считываем HTTP-запрос из сокета, но не больше 0x1000 байт (странно, если запрос будет больше).
        # Параллельно необходимо проверять, что не истек timeout.
        while len(data) < 0x1000:
            # Проверяем сколько времени осталось до истечения timeout.
            # Если времени не осталось, то прерываем чтение.
            left = timer.left
            if left is not None and left < 0:
                break

            # Проверяем, есть ли данные в сокете:
            r, w, x = select([client], [], [], left)
            if client not in r:
                continue

            # Добавляем считанные данные к уже имеюшимся:
            data += client.recv(0x1000 - len(data))

            # Если последние 4 символа - это '\r\n\r\n', то это конец запроса. Прерывем чтение.
            if len(data) > 4 and data[-4:] == b'\r\n\r\n':
                break

        # Если считано больше 0x1000 байт или истек timeout, но в конце запроса нет '\r\n\r\n',
        # то выбросим RequestTimeout
        if len(data) < 4 or data[-4:] != b'\r\n\r\n':
            raise RequestTimeout()

        # Попробуем сформировать ответ:
        response = create_response(data.decode(), validate)
    except BadRequest as exc:
        response = BAD_REQUEST
        error = exc
    except NotFound as exc:
        response = NOT_FOUND
        error = exc
    except MethodNotAllowed as exc:
        response = METHOD_NOT_ALLOWED
        error = exc
    except RequestTimeout as exc:
        response = REQUEST_TIMEOUT
        error = exc
    except UpgradeRequired as exc:
        response = UPGRADE_REQUIRED
        error = exc
    except Exception as exc:
        error = exc

    # Если текст ответа не None, попробуем отправить его обратно клиенту
    if response:
        try:
            client.sendall(response.encode())
        except Exception as exc:
            if error is None:
                error = exc

    # Если во обработки зароса произошла какая-то ошибка, то пробросим ее дальше:
    if error:
        raise error
