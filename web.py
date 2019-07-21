from typing import Optional, Dict, List
from flask import Flask, render_template, request, redirect, url_for
from flask import Response, make_response
from game import Player, Game


app = Flask(__name__, static_url_path='/static')


class FlaskPlayer(Player):
    __id = 0

    def __init__(self, name: str):
        from time import time
        super().__init__(name)
        FlaskPlayer.__id += 1
        self.__id = FlaskPlayer.__id
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
games: Dict[FlaskPlayer, Game] = {}
queue: List[FlaskPlayer] = []


def start_game(player1: FlaskPlayer, player2: FlaskPlayer):
    game = Game(player1, player2)
    games[player1] = game
    games[player2] = game


def enqueue(new_player: FlaskPlayer):
    for i in range(len(queue) - 1, -1, -1):
        player = queue[i]
        if player.expired:
            queue.pop(i)
    queue.append(new_player)
    if len(queue) == 2:
        start_game(*queue)
        queue.clear()
        return True
    return False


def get_player() -> Optional[FlaskPlayer]:
    try:
        cookie = request.cookies['player_id']
        player_id = int(cookie)
        return players[player_id]
    except:
        return None


def player_required(func):
    def wrapper(**kwargs):
        player = get_player()
        if player is None:
            return redirect(url_for('index'))
        return func(player, **kwargs)
    return wrapper


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == "POST":
        return join_post()
    else:
        return join_get()


def join_post():
    player = get_player()
    if player is not None:
        return join_get()

    name = request.form['name']
    player = FlaskPlayer(name)
    players[player.id] = player

    if enqueue(player):
        response = redirect(url_for('game'))
    else:
        response: Response = make_response(render_template('join.html'))

    response.set_cookie('player_id', str(player.id))
    return response


@player_required
def join_get(player: FlaskPlayer):
    player.touch()
    if player in games:
        return redirect(url_for('game'))
    else:
        return render_template('join.html')


@app.route("/game")
@player_required
def game(player1: FlaskPlayer):
    game = games[player1]
    player2 = game.players[0]
    if player1 is player2:
        player2 = game.players[1]
    return render_template('game.html', player1=player1, player2=player2)


app.run()
