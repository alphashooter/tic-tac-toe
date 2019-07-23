from typing import Tuple, List, Optional
from ._player import Player


def get_winner(grid) -> Optional[Player]:
    for row in range(3):
        player = grid[row][0]
        if player is None:
            continue
        for col in range(1, 3):
            if grid[row][col] is not player:
                break
        else:
            return player

    for col in range(3):
        player = grid[0][col]
        if player is None:
            continue
        for row in range(1, 3):
            if grid[row][col] is not player:
                break
        else:
            return player

    player = grid[0][0]
    if player is not None:
        for i in range(1, 3):
            if grid[i][i] is not player:
                break
        else:
            return player

    player = grid[0][2]
    if player is not None:
        for i in range(1, 3):
            if grid[i][2 - i] is not player:
                break
        else:
            return player

    return None


class Game(object):
    __id = 0

    __players: Tuple[Player, Player]
    __current: int
    __grid: List[List[Optional[Player]]]
    __winner: Optional[Player]
    __turns: int

    def __init__(self, player1: Player, player2: Player):
        from time import time
        self.__players = player1, player2
        self.__current = 0
        self.__grid = [[None for i in range(3)] for j in range(3)]
        self.__winner = None
        self.__turns = 0
        Game.__id += 1
        self.__id = int(time()) + Game.__id

    def turn(self, player: Player, x: int, y: int):
        assert player is self.__players[self.__current]
        assert 0 <= x < 3 and 0 <= y < 3
        assert self.__grid[y][x] is None
        assert not self.finished
        self.__grid[y][x] = player
        self.__current = 1 - self.__current
        self.__turns += 1
        self.finish()

    def finish(self) -> None:
        self.__winner = get_winner(self.__grid)

    @property
    def finished(self) -> bool:
        return self.__winner or self.__turns == 9

    @property
    def current(self) -> Player:
        return self.__players[self.__current]

    @property
    def winner(self) -> Optional[Player]:
        return self.__winner

    @property
    def grid(self) -> List[List[Optional[Player]]]:
        return self.__grid
    
    @property
    def players(self):
        return self.__players

    @property
    def id(self):
        return self.__id
