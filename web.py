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


def get_player() -> Optional[FlaskPlayer]:
    try:
        cookie = request.cookies['player_id']
        player_id = int(cookie)
        return players[player_id]
    except:
        return None


def player_required(func):
    def wrapper(*args, **kwargs):
        player = get_player()
        if player is None:
            return redirect(url_for('index'))
        return func(player, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


@app.route('/')
def index():
    player = get_player()
    if player:
        if player in game_by_player:
            return redirect(url_for('game', game_id=game_by_player[player].id))
        else:
            return redirect(url_for('join'))
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

    game = enqueue(player)
    if game:
        response = redirect(url_for('game', game_id=game.id))
    else:
        response: Response = make_response(render_template('join.html'))

    response.set_cookie('player_id', str(player.id))
    return response


@player_required
def join_get(player: FlaskPlayer):
    player.touch()
    if player in game_by_player:
        return redirect(url_for('game', game_id=game_by_player[player].id))
    else:
        if player in queue:
            return render_template('join.html')
        else:
            game = enqueue(player)
            if game:
                return redirect(url_for('game', game_id=game.id))
            else:
                return render_template('join.html')


@app.route("/game/<int:game_id>", methods=['GET', 'POST'])
def game(game_id):
    if request.method == 'GET':
        return game_get(game_id)
    else:
        return game_post(game_id)


@player_required
def game_get(player: FlaskPlayer, game_id: int):
    game = game_by_id[game_id]
    return render_template('game.html', player=player, game=game)


@player_required
def game_post(player: FlaskPlayer, game_id: int):
    game = game_by_id[game_id]
    row, col = map(int, request.form['cell'].split(','))
    game.turn(player, col, row)
    if game.finished:
        del game_by_player[game.players[0]]
        del game_by_player[game.players[1]]
    return render_template('game.html', player=player, game=game)


app.run(host='192.168.0.102')
