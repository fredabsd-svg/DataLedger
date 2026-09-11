from django.contrib.auth.models import AbstractUser
from django.db import models


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
