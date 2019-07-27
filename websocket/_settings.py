import re
import logging

REASON_NORMAL = 1000
REASON_PROTOCOL_ERROR = 1002
REASON_NOT_SUPPORTED = 1003
REASON_MESSAGE = {
    REASON_PROTOCOL_ERROR: 'Protocol error',
    REASON_NOT_SUPPORTED: 'Unknown opcode'
}

OPCODE_TEXT = 0x01
OPCODE_BINARY = 0x02
OPCODE_CLOSE = 0x08
OPCODE_PING = 0x09
OPCODE_PONG = 0x0A
OPCODE_NAME = {
    OPCODE_TEXT: 'text',
    OPCODE_BINARY: 'binary',
    OPCODE_CLOSE: 'close',
    OPCODE_PING: 'ping',
    OPCODE_PONG: 'pong'
}

REQUEST_REGEX = re.compile(r'(\w+) (\S+) HTTP/(\d\.\d)')
HEADER_REGEX = re.compile(r'((?:\w|-)+): (.*)')

logger = logging.getLogger('websocket')
