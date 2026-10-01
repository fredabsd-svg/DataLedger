from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Usuario(AbstractUser):
    """Usuário da plataforma.

    Estende o usuário padrão do Django apenas para exigir e-mail único,
    necessário para recuperação de senha e notificações. O vínculo com
    escritórios (e o papel de cada usuário em cada um) vive em
    apps.tenancy.VinculoUsuarioEscritorio, não aqui: um mesmo usuário pode
    ter papéis diferentes em escritórios diferentes.
    """

    email = models.EmailField("endereço de e-mail", unique=True)

    def __str__(self):
        return self.get_full_name() or self.username


class TentativaDeAcesso(models.Model):
    """Uma tentativa contada contra o limite de login ou de cadastro (DL-056).

    Uma linha por tentativa, e o limite é `COUNT(*)` dentro da janela: sem
    contador mutável para perder atualização concorrente, e "janela deslizante"
    sai de graça. Vive no banco (e não em cache local) porque o gunicorn roda
    vários processos — contador por processo multiplicaria o limite pelo
    número de processos.

    `chave` NUNCA guarda o texto digitado no campo de usuário: em `login_usuario`
    é um HMAC do usuário normalizado (o campo de usuário já recebeu senha
    digitada no lugar errado — BL-555/B3). Em `*_ip` é o próprio endereço.
    Linhas vencidas são apagadas de forma oportunista
    (`limite_tentativas.limpar_vencidas`); não há tarefa em segundo plano.
    """

    class Escopo(models.TextChoices):
        LOGIN_USUARIO = "login_usuario", "Login, por usuário digitado"
        LOGIN_IP = "login_ip", "Login, por endereço IP"
        CADASTRO_IP = "cadastro_ip", "Cadastro de escritório, por endereço IP"

    escopo = models.CharField(max_length=20, choices=Escopo.choices)
    chave = models.CharField(max_length=64)
    registrado_em = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            # Consulta do limite: (escopo, chave) por igualdade + faixa de tempo.
            models.Index(fields=["escopo", "chave", "registrado_em"], name="tentativa_limite_idx"),
            # Limpeza oportunista: varre só o que venceu.
            models.Index(fields=["registrado_em"], name="tentativa_venc_idx"),
        ]

    def __str__(self):
        return f"{self.escopo} @ {self.registrado_em:%Y-%m-%d %H:%M:%S}"
