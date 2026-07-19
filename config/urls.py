from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from core.auth import UsuarioLoginView, logout_and_cleanup

urlpatterns = [
    path("admin/", admin.site.urls),
    # Páginas legais (LGPD): acessíveis sem login.
    path("privacidade/", TemplateView.as_view(template_name="legal/privacidade.html"), name="privacidade"),
    path("termos/", TemplateView.as_view(template_name="legal/termos.html"), name="termos"),
    path("login/", UsuarioLoginView.as_view(), name="login"),
    path("logout/", logout_and_cleanup, name="logout"),
    path("", include(("core.urls", "core"), namespace="core")),
    path("fontes/", include(("fonts.urls", "fonts"), namespace="fonts")),
    path("templates/", include(("editor.urls", "editor"), namespace="editor")),
    path("jobs/", include(("jobs.urls", "jobs"), namespace="jobs")),
]
