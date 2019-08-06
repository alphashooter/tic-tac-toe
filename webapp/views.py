from django.shortcuts import render
from django.http.response import *

# Create your views here.


def index(request):
    return HttpResponse(b'hello, world!')


def hello(request, name):
    return render(request, "hello.html", {'name': name})
