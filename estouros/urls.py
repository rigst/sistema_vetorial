from django.urls import path

from .views import (
    BaixarArquivoView,
    BaixarZipView,
    EstouroView,
    ExcluirLoteView,
    LoteStatusView,
    PreviaArquivoView,
)

app_name = "estouros"

urlpatterns = [
    path("", EstouroView.as_view(), name="inicio"),
    path("<int:pk>/", EstouroView.as_view(), name="lote"),
    path("<int:pk>/status/", LoteStatusView.as_view(), name="status"),
    path("<int:pk>/zip/", BaixarZipView.as_view(), name="baixar-zip"),
    path("<int:pk>/excluir/", ExcluirLoteView.as_view(), name="excluir"),
    path("arquivo/<int:pk>/", BaixarArquivoView.as_view(), name="baixar"),
    path("arquivo/<int:pk>/previa/", PreviaArquivoView.as_view(), name="previa"),
]
