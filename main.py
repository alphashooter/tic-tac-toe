from game import *

name1 = input('Player #1 name: ')
player1 = Player(name1)

name2 = input('Player #2 name: ')
player2 = Player(name2)

marks = {player1: 'x', player2: 'o', None: ' '}

game = Game(player1, player2)
while not game.finished:
    current = game.current

    print('\n' * 100)
    print('+---+---+---+')
    for row in game.grid:
        print('| ' + ' | '.join(map(marks.get, row)) + ' |')
        print('+---+---+---+')

    while True:
        turn = input(f'{current.name}\'s turn: ')
        try:
            x, y = map(int, turn.split(','))
            game.turn(current, x, y)
        except:
            print('invalid input')
        else:
            break

print('\n' * 100)
print('+---+---+---+')
for row in game.grid:
    print('| ' + ' | '.join(map(marks.get, row)) + ' |')
    print('+---+---+---+')

if game.winner:
    print(f'Congratulations, {game.winner.name}!')
else:
    print(';(')
