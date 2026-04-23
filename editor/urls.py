from django.urls import path

from .views import (
    DocumentTemplateCreateView,
    DocumentTemplateDeleteView,
    DocumentTemplateDetailView,
    DocumentTemplateDuplicateView,
    DocumentTemplateListView,
    DocumentTemplateUpdateView,
    TemplatePreviewPageImageView,
    TemplateLayoutUpdateView,
    TemplateFieldDeleteView,
    TemplateFieldCreateView,
    TemplateFieldUpdateView,
)

app_name = "editor"

urlpatterns = [
    path("", DocumentTemplateListView.as_view(), name="list"),
    path("novo/", DocumentTemplateCreateView.as_view(), name="create"),
    path("<int:pk>/", DocumentTemplateDetailView.as_view(), name="detail"),
    path("<int:pk>/editar/", DocumentTemplateUpdateView.as_view(), name="update"),
    path("<int:pk>/preview/<int:page_number>/", TemplatePreviewPageImageView.as_view(), name="preview-page"),
    path("<int:pk>/duplicar/", DocumentTemplateDuplicateView.as_view(), name="duplicate"),
    path("<int:pk>/excluir/", DocumentTemplateDeleteView.as_view(), name="delete"),
    path("<int:pk>/layout/", TemplateLayoutUpdateView.as_view(), name="layout-update"),
    path("<int:template_pk>/campos/novo/", TemplateFieldCreateView.as_view(), name="field-create"),
    path("campos/<int:pk>/editar/", TemplateFieldUpdateView.as_view(), name="field-update"),
    path("campos/<int:pk>/excluir/", TemplateFieldDeleteView.as_view(), name="field-delete"),
]
