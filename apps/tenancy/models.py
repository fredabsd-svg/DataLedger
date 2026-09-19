from django.conf import settings
from django.db import models
from django.utils.crypto import get_random_string


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


class ConviteEscritorio(models.Model):
    """Convite escrito pelo ADMINISTRADOR do escritório para o e-mail do
    segundo funcionário (DE-042 / DL-018).

    O convite NÃO vincula o usuário — apenas o torna elegível. O
    vínculo é criado em `aceitar_convite_e_criar_vinculo`, com o
    usuário autenticado apresentando o token. Esta separação é a
    defesa contra o cenário "convidado mal intencionado cria conta
    com e-mail de terceiro".

    Prazo: 7 dias desde a emissão. Convite expirado: o campo
    `consumido_em` permanece `NULL` (a expiração é derivada do
    `criado_em` + 7 dias, não de um campo gravado), e a consulta de
    "exibível / consumível" precisa cruzar a data atual — isto é
    feito no serviço, não no banco, para que a janela do convite possa
    ser ajustada sem migração.
    """

    escritorio = models.ForeignKey(
        Escritorio,
        verbose_name="escritório",
        on_delete=models.CASCADE,
        related_name="convites",
    )
    email = models.EmailField("e-mail do convidado")
    papel_inicial = models.CharField(
        "papel inicial", max_length=20, choices=Papel.choices, default=Papel.ANALISTA
    )
    token = models.CharField(
        "token de aceite",
        max_length=64,
        unique=True,
        help_text="Token opaco apresentado em /convite/<token>/. Único por convite.",
    )
    emitido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="emitido por",
        on_delete=models.PROTECT,
        related_name="convites_emitidos",
    )
    criado_em = models.DateTimeField("criado em", auto_now_add=True)
    consumido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="consumido por",
        on_delete=models.PROTECT,
        related_name="convites_consumidos",
        null=True,
        blank=True,
    )
    consumido_em = models.DateTimeField("consumido em", null=True, blank=True)

    class Meta:
        verbose_name = "convite escritório"
        verbose_name_plural = "convites escritório"
        ordering = ["-criado_em"]

    def __str__(self):
        return f"Convite {self.email} → {self.escritorio}"

    @property
    def expirado(self) -> bool:
        """7 dias desde a emissão."""
        from datetime import timedelta

        from django.utils import timezone

        return timezone.now() > (self.criado_em + timedelta(days=7))

    def save(self, *args, **kwargs):
        """Gera um token opaco de 32 chars base64-url no `save` se o
        token ainda não está definido. 32 chars de `get_random_string`
        rendem ~190 bits de entropia — o suficiente para não caber em
        ataque de dicionário. O token é gravado **antes** do `super().save`,
        porque o `unique=True` precisa do valor no INSERT.

        Re-geração se o token colidir com um convite existente: o loop
        aqui é teórico (probabilidade de colisão ≈ 1 em 2^190), mas
        mantém o invariante `unique=True` sem precisar de migração.
        """
        if not self.token:
            while True:
                candidato = get_random_string(32)
                if not ConviteEscritorio.objects.filter(token=candidato).exists():
                    self.token = candidato
                    break
        super().save(*args, **kwargs)
