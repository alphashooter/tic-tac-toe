from threading import Thread, Lock


counter = 0
lock = Lock()


def enter():
    global counter
    while True:
        lock.acquire()
        counter += 1
        j = counter
        assert counter == j, f'{counter} != {j}'
        lock.release()


n = 2
for i in range(n):
    Thread(target=enter).start()
