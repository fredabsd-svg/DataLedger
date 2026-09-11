from django.conf import settings
from django.db import models


class Escritorio(models.Model):
    """Escritório de contabilidade: raiz do isolamento multiempresa.

    Toda regra de negócio dos módulos (Fiscal, Folha, Contabilidade,
    Honorários, Processos) deve, direta ou indiretamente, referenciar um
    Escritorio e nunca cruzar dados entre escritórios diferentes.
    """

    nome = models.CharField("nome", max_length=200)
    cnpj = models.CharField("CNPJ", max_length=14, unique=True)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "escritório"
        verbose_name_plural = "escritórios"
        ordering = ["nome"]

    def __str__(self):
        return self.nome


class Papel(models.TextChoices):
    """Perfis previstos no escopo funcional (docs/escopo.md).

    A matriz fina de permissões por módulo e operação é tratada em uma
    etapa futura; o papel aqui é a informação mínima de autorização já
    necessária para o isolamento entre escritórios.
    """

    ADMINISTRADOR = "administrador", "Administrador"
    GESTOR = "gestor", "Gestor"
    ANALISTA = "analista", "Analista"
    FINANCEIRO = "financeiro", "Financeiro"
    PARALEGAL = "paralegal", "Paralegal"
    CLIENTE = "cliente", "Cliente"


class VinculoUsuarioEscritorio(models.Model):
    """Associa um usuário a um escritório com um papel.

    É a base do isolamento entre escritórios: nenhuma consulta de dados de
    negócio deve ignorar este vínculo. Um usuário pode estar vinculado a
    mais de um escritório (ex.: contador que atende como suporte em outro
    escritório), cada vínculo com seu próprio papel.
    """

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuário",
        on_delete=models.CASCADE,
        related_name="vinculos",
    )
    escritorio = models.ForeignKey(
        Escritorio,
        verbose_name="escritório",
        on_delete=models.CASCADE,
        related_name="vinculos",
    )
    papel = models.CharField("papel", max_length=20, choices=Papel.choices)
    ativo = models.BooleanField("ativo", default=True)
    criado_em = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "vínculo usuário-escritório"
        verbose_name_plural = "vínculos usuário-escritório"
        constraints = [
            models.UniqueConstraint(
                fields=["usuario", "escritorio"],
                name="unico_vinculo_usuario_escritorio",
            ),
        ]

    def __str__(self):
        return f"{self.usuario} @ {self.escritorio} ({self.get_papel_display()})"
