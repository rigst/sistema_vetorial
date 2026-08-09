from django.contrib import admin
from django.urls import include, path

from core.auth import UsuarioLoginView, logout_and_cleanup
from legal import views as legal_views

urlpatterns = [
    path("admin/", admin.site.urls),
    # Páginas legais (LGPD): acessíveis sem login. O texto vem do banco (app
    # `legal`), versionado — os nomes de rota seguem os mesmos de antes.
    path("privacidade/", legal_views.privacidade, name="privacidade"),
    path("termos/", legal_views.termos, name="termos"),
    path("legal/", include("legal.urls")),
    path("login/", UsuarioLoginView.as_view(), name="login"),
    path("logout/", logout_and_cleanup, name="logout"),
    path("", include(("core.urls", "core"), namespace="core")),
    path("fontes/", include(("fonts.urls", "fonts"), namespace="fonts")),
    path("templates/", include(("editor.urls", "editor"), namespace="editor")),
    path("jobs/", include(("jobs.urls", "jobs"), namespace="jobs")),
]
