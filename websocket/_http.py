from typing import Tuple, Dict
from ._settings import *


def parse_http(data: str) -> Tuple[str, str, str, Dict[str, str]]:
    """
    Разбивает строку с HTTP-запросом на метод, URI, версию HTTP и заголовки.

    Запрос должен иметь вид:
    ::
        {method} {uri} HTTP/{version}\\r\\n
        {header-name}: {header-value}\\r\\n
        ...
        \\r\\n

    Например:
    ::
        GET /path/to/resource HTTP/1.1\\r\\n
        Host: www.example.com\\r\\n
        Connection: close\\r\\n
        \\r\\n

    Результатом разбиения такого запроса будет кортеж:
    ::
        "GET", "/path/to/resource", "1.1", {"Host": "www.example.com", "Connection": "close"}

    :param data: текст HTTP-запроса
    :return: Метод, URI, версия HTTP и заголовки запроса
    """
    # Запрос должен заканчиваться '\r\n\r\n'
    assert len(data) > 4 and data[-4:] == '\r\n\r\n', 'HTTP request is not terminated'
    # Разбиваем исходный запрос на строки по '\r\n'
    lines = data[:-4].split('\r\n')
    # Первая строка запроса - это метод, URI и версия HTTP
    method, uri, version = parse_http_request(lines[0])
    # Остальные строки - это заголовки
    headers = dict(map(parse_http_header, lines[1:]))
    return method, uri, version, headers


def parse_http_request(data: str):
    """
    Разбивает первую строку запроса на метод, URI и версию HTTP

    :param data: текст первой строки HTTP-зароса
    :return: Метод, URI и версия HTTP
    """
    match = REQUEST_REGEX.match(data)
    assert match, 'Invalid HTTP request'
    return match.group(1), match.group(2), match.group(3)


def parse_http_header(data: str):
    """
    Разбивает строку заголовка запроса на имя заголовка и его значение

    :param data: текст строки заголовка HTTP-запроса
    :return: Имя заголовка и значение
    """
    match = HEADER_REGEX.match(data)
    assert match, 'Invalid HTTP header'
    return match.group(1), match.group(2)
