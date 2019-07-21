from typing import Dict, List
from flask import Flask, render_template, request, redirect
from flask import Response, make_response
from game import Player, Game


app = Flask(__name__)


class FlaskPlayer(Player):
    __id = 0

    def __init__(self, name: str):
        from time import time
        super().__init__(name)
        FlaskPlayer.__id += 1
        self.__id = FlaskPlayer.__id
        self.__last_activity = time()

    @property
    def expired(self):
        from time import time
        now = time()
        delta = now - self.__last_activity
        return delta > 60

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


@app.route('/')
def index():
    return render_template("index.html")


@app.route('/join', methods=['GET', 'POST'])
def join():
    if request.method == "POST":
        name = request.form['name']

        player = FlaskPlayer(name)
        players[player.id] = player

        if enqueue(player):
            response = redirect('/game')
        else:
            response: Response = make_response(render_template('join.html'))

        response.set_cookie('player_id', str(player.id))
        return response
    else:
        player_id = int(request.cookies.get('player_id', 0))
        player = players.get(player_id, None)
        if not player:
            return redirect('/')
        else:
            if player in games:
                return redirect('/game')
            else:
                return render_template('join.html')


@app.route("/game")
def game():
    player_id = int(request.cookies["player_id"])
    player1 = players[player_id]
    game = games[player1]
    player2 = game.players[0]
    if player1 is player2:
        player2 = game.players[1]
    return render_template('game.html', player1=player1, player2=player2)


app.run()
