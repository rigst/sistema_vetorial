from django.urls import path

from .views import (
    DocumentTemplatePreviewView,
    DocumentTemplateCreateView,
    DocumentTemplateDeleteView,
    DocumentTemplateDetailView,
    DocumentTemplateDuplicateView,
    DocumentTemplateListView,
    DocumentTemplateUpdateView,
    TemplateFieldApiView,
    TemplatePreviewPageImageView,
    TemplateFieldsApiView,
    TemplateLayoutUpdateView,
    TemplateSampleDataView,
)

app_name = "editor"

urlpatterns = [
    path("", DocumentTemplateListView.as_view(), name="list"),
    path("novo/", DocumentTemplateCreateView.as_view(), name="create"),
    path("<int:pk>/", DocumentTemplateDetailView.as_view(), name="detail"),
    path("<int:pk>/visualizar/", DocumentTemplatePreviewView.as_view(), name="preview"),
    path("<int:pk>/editar/", DocumentTemplateUpdateView.as_view(), name="update"),
    path("<int:pk>/preview/<int:page_number>/", TemplatePreviewPageImageView.as_view(), name="preview-page"),
    path("<int:pk>/duplicar/", DocumentTemplateDuplicateView.as_view(), name="duplicate"),
    path("<int:pk>/excluir/", DocumentTemplateDeleteView.as_view(), name="delete"),
    path("<int:pk>/layout/", TemplateLayoutUpdateView.as_view(), name="layout-update"),
    path("<int:pk>/campos/", TemplateFieldsApiView.as_view(), name="fields-api"),
    path("<int:pk>/amostra/", TemplateSampleDataView.as_view(), name="sample-data"),
    path("campos/<int:pk>/", TemplateFieldApiView.as_view(), name="field-api"),
]
