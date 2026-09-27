"""Serializers do livro-caixa (DL-046, fatia 1) — só SAÍDA.

A CRIAÇÃO de `ContaLivroCaixa` e de `LancamentoCaixa` não passa por
`serializer.save()`: a view extrai e valida o corpo (política dos cinco
dicionários, BL-196) e chama o SERVIÇO
(`apps.livro_caixa.services.criar_conta_livro_caixa`/
`criar_lancamento_caixa`), que grava com `full_clean()` e trilha de
auditoria na mesma transação — mesmo desenho de
`apps.contabilidade.views.LancamentoListCreateView.post`, que também não usa
um serializer de entrada para o lançamento. Estes serializers servem só para
formatar a RESPOSTA (GET e o corpo devolvido depois de um POST bem-sucedido).
"""

from rest_framework import serializers

from apps.livro_caixa.models import ContaLivroCaixa, DependentesCarneLeaoCliente, LancamentoCaixa


class ContaLivroCaixaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContaLivroCaixa
        fields = [
            "id",
            "codigo",
            "nome",
            "natureza",
            "codigo_carne_leao",
            # DL-046, fatia 3 (RC-127/HI-34).
            "codigo_ocupacao",
            "ativa",
            "criado_em",
        ]
        read_only_fields = fields


class LancamentoCaixaSerializer(serializers.ModelSerializer):
    conta_codigo = serializers.CharField(source="conta.codigo", read_only=True)
    conta_nome = serializers.CharField(source="conta.nome", read_only=True)

    class Meta:
        model = LancamentoCaixa
        fields = [
            "id",
            "conta",
            "conta_codigo",
            "conta_nome",
            "data",
            "valor",
            "historico",
            "documento_origem",
            "recebido_de",
            "cpf_titular_pagamento",
            "cpf_beneficiario_servico",
            "cpf_beneficiario_nao_informado",
            "cnpj_pagador",
            # DL-046, fatia 3 (RC-127).
            "valor_irrf",
            "competencia_previdencia",
            "multa_previdencia",
            "juros_previdencia",
            "estorno_de",
            "criado_em",
        ]
        read_only_fields = fields


class DependentesCarneLeaoClienteSerializer(serializers.ModelSerializer):
    """DL-046, fatia 2 — só SAÍDA (mesmo desenho dos dois serializers acima):
    a gravação passa por `apps.livro_caixa.carne_leao.
    registrar_dependentes_carne_leao`, nunca por `serializer.save()`."""

    class Meta:
        model = DependentesCarneLeaoCliente
        fields = ["id", "quantidade", "competencia_inicio", "criado_em"]
        read_only_fields = fields
