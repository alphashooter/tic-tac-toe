from socket import socket, AF_INET, SOCK_STREAM, IPPROTO_TCP
from websocket import WebSocket
import logging

logging.basicConfig(level=logging.DEBUG)

server = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP)
server.bind(('127.0.0.1', 5001))
server.listen(1)

client, addr = server.accept()
server.close()

ws = WebSocket(client)
ws.accept()

assert ws.ping(5)
print(ws.recv())

for i in range(3):
    ws.send(f'hello #{1 + i}')

ws.close()

# from js console:
# socket = new WebSocket('127.0.0.1:5001')
# socket.onmessage = console.log
# socket.onclose = console.log
# socket.send('hello!')
