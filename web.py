from flask import Flask, Response, make_response


app = Flask(__name__)


# http://localhost:5000/
@app.route('/')
def index():
    return 'Hello, World!'


# http://localhost:5000/hello/Bob
@app.route('/hello/<name>')
def hello1(name):
    return f'Hello, {name}!'


# http://localhost:5000/hello/James_Bond
@app.route('/hello/<name>_<surname>')
def hello2(name, surname):
    return f'{surname}. {name} {surname}.'


# Для работы необходимо, чтобы в проекте лежала картинка с именем pic.jpg
# http://localhost:5000/image/pic.jpg
@app.route('/picture/<path>')
def picture(path):
    with open(path, 'rb') as file:
        data = file.read()
    response: Response = make_response(data)
    response.headers['Content-Type'] = 'image/jpeg'
    return response


app.run()
