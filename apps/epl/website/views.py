from django.http import HttpResponse


def index(request):
    return HttpResponse("EPL Bets — powered by vinosports-core")
