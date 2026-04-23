from django.urls import path

from .views import (
    GenerationJobCreateView,
    GenerationJobDetailView,
    GenerationJobListView,
    GenerationJobStatusView,
    PromotePreviewJobView,
)

app_name = "jobs"

urlpatterns = [
    path("", GenerationJobListView.as_view(), name="list"),
    path("novo/", GenerationJobCreateView.as_view(), name="create"),
    path("<int:pk>/", GenerationJobDetailView.as_view(), name="detail"),
    path("<int:pk>/status/", GenerationJobStatusView.as_view(), name="status"),
    path("<int:pk>/gerar-lote/", PromotePreviewJobView.as_view(), name="promote"),
]
