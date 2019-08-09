from django.shortcuts import render, redirect, reverse
from django.http.response import HttpResponse
from django.http.request import *

from typing import Dict, List, Optional
from game import Player, Game

# Create your views here.


class FlaskPlayer(Player):
    __id = 0

    def __init__(self, name: str):
        from time import time
        super().__init__(name)
        FlaskPlayer.__id += 1
        self.__id = (int(time()) << 8) | FlaskPlayer.__id
        self.__last_activity = time()

    def touch(self) -> None:
        from time import time
        self.__last_activity = time()

    @property
    def expired(self):
        from time import time
        now = time()
        delta = now - self.__last_activity
        return delta > 30

    @property
    def id(self):
        return self.__id


players: Dict[int, FlaskPlayer] = {}
game_by_player: Dict[FlaskPlayer, Game] = {}
game_by_id: Dict[int, Game] = {}
queue: List[FlaskPlayer] = []


def start_game(player1: FlaskPlayer, player2: FlaskPlayer):
    game = Game(player1, player2)
    game_by_player[player1] = game
    game_by_player[player2] = game
    game_by_id[game.id] = game
    return game


def enqueue(new_player: FlaskPlayer):
    for i in range(len(queue) - 1, -1, -1):
        player = queue[i]
        if player.expired:
            queue.pop(i)
    queue.append(new_player)
    if len(queue) == 2:
        game = start_game(*queue)
        queue.clear()
        return game
    return None


def get_player(request: HttpRequest) -> Optional[FlaskPlayer]:
    try:
        cookie = request.COOKIES['player_id']
        player_id = int(cookie)
        return players[player_id]
    except:
        return None


def player_required(func):
    def wrapper(request: HttpRequest, *args, **kwargs):
        player = get_player(request)
        if player is None:
            return redirect(reverse('index'))
        return func(request, player, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def index(request: HttpRequest):
    player = get_player(request)
    if player:
        if player in game_by_player:
            return redirect(reverse('game', kwargs={'game_id': game_by_player[player].id}))
        else:
            return redirect(reverse('join'))
    return render(request, "index.html")


def join(request: HttpRequest):
    if request.method == "POST":
        return join_post(request)
    else:
        return join_get(request)


def join_post(request: HttpRequest):
    player = get_player(request)
    if player is not None:
        return join_get(request)

    name = request.POST['name']
    player = FlaskPlayer(name)
    players[player.id] = player

    game = enqueue(player)
    if game:
        response = redirect(reverse('game', kwargs={'game_id': game.id}))
    else:
        response = render(request, 'join.html')

    response.set_cookie('player_id', str(player.id))
    return response


@player_required
def join_get(request: HttpRequest, player: FlaskPlayer):
    player.touch()
    if player in game_by_player:
        return redirect(reverse('game', kwargs={'game_id': game_by_player[player].id}))
    else:
        if player in queue:
            return render(request, 'join.html')
        else:
            game = enqueue(player)
            if game:
                return redirect(reverse('game', kwargs={"game_id": game.id}))
            else:
                return render(request, 'join.html')


def game(request: HttpRequest, game_id):
    if request.method == 'GET':
        return game_get(request, game_id)
    else:
        return game_post(request, game_id)


@player_required
def game_get(request, player: FlaskPlayer, game_id: int):
    game = game_by_id[game_id]
    return render(request, 'game.html', {'player': player, 'game': game})


@player_required
def game_post(request: HttpRequest, player: FlaskPlayer, game_id: int):
    game = game_by_id[game_id]
    row, col = map(int, request.POST['cell'].split(','))
    game.turn(player, col, row)
    if game.finished:
        del game_by_player[game.players[0]]
        del game_by_player[game.players[1]]
    return render(request, 'game.html', {'player': player, 'game': game})
