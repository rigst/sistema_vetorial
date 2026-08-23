from django.urls import path

from .views import HomeView, criar_visitante

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("visitante/entrar/", criar_visitante, name="criar_visitante"),
]
