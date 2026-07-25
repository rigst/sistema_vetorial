from django.urls import path

from .views import (
    GenerationJobCreateView,
    GenerationJobDeleteView,
    GenerationJobDetailView,
    GenerationJobListView,
    GenerationJobSourceExcelDownloadView,
    GenerationItemDownloadView,
    GenerationJobZipDownloadView,
    GenerationJobLaunchApiView,
    GenerationJobStatusView,
    PromotePreviewJobView,
    RerunJobView,
)

app_name = "jobs"

urlpatterns = [
    path("", GenerationJobListView.as_view(), name="list"),
    path("novo/", GenerationJobCreateView.as_view(), name="create"),
    path("<int:pk>/", GenerationJobDetailView.as_view(), name="detail"),
    path("<int:pk>/excluir/", GenerationJobDeleteView.as_view(), name="delete"),
    path("<int:pk>/status/", GenerationJobStatusView.as_view(), name="status"),
    path("lancar/", GenerationJobLaunchApiView.as_view(), name="launch"),
    path("<int:pk>/rerun/", RerunJobView.as_view(), name="rerun"),
    path("<int:pk>/download/source/", GenerationJobSourceExcelDownloadView.as_view(), name="download-source"),
    path("<int:pk>/download/zip/", GenerationJobZipDownloadView.as_view(), name="download-zip"),
    path("item/<int:pk>/download/", GenerationItemDownloadView.as_view(), name="download-item"),
    path("<int:pk>/gerar-lote/", PromotePreviewJobView.as_view(), name="promote"),
]
