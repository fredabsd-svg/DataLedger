from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/", include("apps.core.urls")),
    path("api/auditoria/", include("apps.auditoria.urls")),
    path("empresas/", include("apps.empresas.urls")),
    path("contabilidade/", include("apps.contabilidade.urls")),
    # Telas da contabilidade (DL-017). Prefixo DIFERENTE do da API acima, e
    # não por gosto: os dois conjuntos têm rotas com o mesmo caminho literal
    # sob o mesmo `empresa_id` (`diario/`, `balancete/`). Se dividissem o
    # prefixo, a segunda inclusão nunca seria alcançada — o Django resolve a
    # primeira que casar, em silêncio, e a tela ou a API simplesmente
    # desapareceria sem erro nenhum. Levantado pelo `especialista-frontend`
    # ao entregar a fase B.
    path("contabilidade/painel/", include("apps.contabilidade.urls_web")),
    path("", include("apps.tenancy.urls")),
]
