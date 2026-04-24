from django.urls import path

from .auth import ManualView
from .views import HomeView

app_name = "core"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("manual/", ManualView.as_view(), name="manual"),
]
