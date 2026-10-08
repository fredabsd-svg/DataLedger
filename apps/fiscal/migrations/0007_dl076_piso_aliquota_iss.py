# DL-076 (auditoria, A9): piso de 2% no banco para a alíquota do ISS por município.
#
# Migração ADITIVA: uma restrição CHECK nova na tabela de alíquotas (que a 0006 criou). Nenhuma
# linha é alterada; se houvesse linha com alíquota abaixo de 2% fora da exceção, a migração
# falharia, o que é o comportamento desejado.
#
# Fonte: LC 116/2003, art. 8º-A (mínimo de 2%) e § 1º (exceção: subitens 7.02, 7.05 e 16.01),
# conferidos na consulta da DL-076 em 08/10/2026. O serviço (apps.fiscal.iss_municipal) já
# recusa a faixa na entrada; o banco segura a mesma regra para o caso de o ORM ser usado direto.
#
# DEPENDÊNCIA: só `fiscal 0006`. A operação toca apenas a tabela de alíquotas, e a 0006 já
# depende de `empresas`, `tenancy` e do usuário. A regra de não acrescentar dependência de
# `empresas` além da 0007 é a lição da DL-075, repetida na ordem desta correção.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("fiscal", "0006_dl076_iss_municipal"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="aliquotaissmunicipal",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("percentual__gte", 2),
                    ("subitem__in", ["07.02", "07.05", "16.01"]),
                    _connector="OR",
                ),
                name="aliquota_iss_piso_2_salvo_excecao",
            ),
        ),
    ]
