from flask import Flask


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


app.run()
