from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.forms import LoginForm
from apps.accounts.views import cadastro

urlpatterns = [
    path("cadastro/", cadastro, name="cadastro"),
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html", authentication_form=LoginForm
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("api/", include("apps.core.urls")),
    path("api/auditoria/", include("apps.auditoria.urls")),
    path("empresas/", include("apps.empresas.urls")),
    path("modulos/", include("apps.core.urls_home")),
    path("contabilidade/", include("apps.contabilidade.urls")),
    # DL-046 fatia 1: livro-caixa e carnê-leão do cliente pessoa física
    # (RC-113/RC-114) — API própria, servidor + API; a tela vem depois pelo
    # frontend. Prefixo diferente de "contabilidade/" de propósito: os dois
    # regimes de escrituração nunca compartilham rota (`recusar_se_livro_
    # caixa`/`recusar_se_nao_livro_caixa` já impedem no servidor; URLs
    # diferentes evitam até a AMBIGUIDADE de qual API responde a uma
    # empresa).
    path("livro-caixa/", include("apps.livro_caixa.urls")),
    # Telas da contabilidade (DL-017). Prefixo DIFERENTE do da API acima, e
    # não por gosto: os dois conjuntos têm rotas com o mesmo caminho literal
    # sob o mesmo `empresa_id` (`diario/`, `balancete/`). Se dividissem o
    # prefixo, a segunda inclusão nunca seria alcançada — o Django resolve a
    # primeira que casar, em silêncio, e a tela ou a API simplesmente
    # desapareceria sem erro nenhum. Levantado pelo `especialista-frontend`
    # ao entregar a fase B.
    path("contabilidade/painel/", include("apps.contabilidade.urls_web")),
    # Telas do livro-caixa (DL-046, fatia 1). Prefixo "livro-caixa/painel/"
    # — DIFERENTE do da API acima ("livro-caixa/") pelo MESMO motivo que
    # levou "contabilidade/painel/" a existir (ver o comentário logo
    # acima): rotas com o mesmo caminho literal ("contas/", "lancamentos/")
    # sob o mesmo `empresa_id`.
    path("livro-caixa/painel/", include("apps.livro_caixa.urls_web")),
    # API da escrituração das NFS-e prestadas (DL-072, frente A). "fiscal/api/"
    # vem ANTES de "fiscal/" para que o prefixo das telas nunca a engula.
    path("fiscal/api/", include("apps.fiscal.urls_api")),
    # Telas da recepção de documentos fiscais (DL-010, fatia 1, etapa 2).
    # Prefixo "fiscal/". A API da escrituração (DL-072) fica em "fiscal/api/",
    # acima, e não colide com estas telas porque é montada antes.
    # Esta fatia da recepção não tinha API REST (DL-010-F1); a API atual é
    # a da DL-072.
    path("fiscal/", include("apps.fiscal.urls_web")),
    path("", include("apps.tenancy.urls")),
]
