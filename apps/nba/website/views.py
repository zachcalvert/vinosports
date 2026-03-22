from django.http import HttpResponse


def index(request):
    return HttpResponse("NBA Bets — powered by vinosports-core")
