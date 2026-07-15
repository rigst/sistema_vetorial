from django.urls import path

from .views import (
    FontAssetCreateView,
    FontAssetDeleteView,
    FontAssetFileView,
    FontAssetListView,
    FontAssetUpdateView,
)

app_name = "fonts"

urlpatterns = [
    path("", FontAssetListView.as_view(), name="list"),
    path("novo/", FontAssetCreateView.as_view(), name="create"),
    path("<int:pk>/editar/", FontAssetUpdateView.as_view(), name="update"),
    path("<int:pk>/excluir/", FontAssetDeleteView.as_view(), name="delete"),
    path("<int:pk>/arquivo/", FontAssetFileView.as_view(), name="file"),
]
