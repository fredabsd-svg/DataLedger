from django import forms

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao


class EmpresaForm(forms.ModelForm):
    """Formulário de cadastro de empresa pela tela (DL-038, etapa 2 — R1,
    R4, R7, HI-23).

    Não precisa declarar nem normalizar "cnpj"/"cpf" aqui: os dois campos
    do modelo são CNPJModelField/CPFModelField (apps/empresas/fields.py),
    cujo formfield() já devolve CNPJFormField/CPFFormField com a
    normalização embutida em to_python() — herdado por qualquer ModelForm
    (esta tela, o admin, um inline futuro), sem duplicar a lógica. É a
    correção estrutural do achado R2 da reauditoria da etapa DL-011,
    preservada aqui sem mudança.

    Quatro decisões de TELA, documentadas aqui porque a "regra" delas é de
    INTERFACE, não de modelo nem de API:

    1. **Sem esconder campo com JavaScript** (direcao-de-arte.md §4.6:
       "JavaScript é enfeite; nenhum dado existe só porque um script
       rodou"). `tipo_inscricao` e `modo_escrituracao` viram grupo de
       radio buttons (widget RadioSelect, ver `__init__`) com as opções
       SEMPRE visíveis; `cnpj` e `cpf` aparecem os dois no formulário,
       nunca um escondido por script atrás do outro.

    2. **R7** — nenhum campo próprio de pessoa JURÍDICA (NIRE,
       estabelecimento) é oferecido aqui. Não é uma omissão desta etapa:
       `Meta.fields`, desde antes da DL-038, já não os incluía — não há
       nada para "esconder" quando o tipo é CPF, porque nunca apareceu
       para nenhum tipo.

    3. **Obrigatoriedade CRUZADA de cnpj/cpf, com a MESMA mensagem em dois
       momentos diferentes.** Qual dos dois é obrigatório depende do que o
       contador marcou em `tipo_inscricao` — não dá para fixar
       `required=True`/`False` por campo (um `ModelForm` só sabe fazer
       isso do jeito FIXO, herdado do modelo). A solução, em `__init__`,
       lê o `tipo_inscricao` BRUTO do próprio POST (`self.data`, antes de
       `clean()` existir) e ajusta `required` de `cnpj`/`cpf` para aquele
       envio — o que faz o Django usar a MESMA mensagem padrão
       ("Este campo é obrigatório.") que o campo já usava antes desta
       etapa, quando só existia CNPJ (compatibilidade preservada: um
       cadastro que não sabe que "tipo de inscrição" existe, e por isso
       nunca o envia, continua tratado como CNPJ, exatamente como sempre
       foi). Quando o contador ESCOLHE o campo ERRADO para o tipo
       marcado (ex.: tipo CPF com `cnpj` também preenchido), a mensagem
       específica de exclusividade mora em `clean()`, abaixo — MESMA regra
       e MESMA mensagem de `EmpresaSerializer.validate`
       (apps/empresas/serializers.py), para tela e API nunca contarem duas
       histórias diferentes ao contador (DE-026).

    4. **HI-23** (hipótese, não confirmada pelo Fred): empresa CPF nova
       SUGERE livro-caixa, e o contador pode trocar. Sem JavaScript, a
       tela não pode reagir à escolha de `tipo_inscricao` ANTES do envio
       para pré-marcar a opção "certa" de `modo_escrituracao` — as duas
       perguntas chegam ao servidor juntas, no mesmo POST. O desenho
       escolhido, entre os dois exemplos do plano: `modo_escrituracao`
       fica OPCIONAL na tela (nenhuma opção vem pré-marcada — forçar uma
       escolha visível, não um padrão invisível), e quando o contador não
       marca nenhuma, `clean()` decide pela sugestão: livro-caixa para
       CPF, contabilidade para CNPJ (mantendo, para CNPJ, o MESMO padrão
       que já valia antes desta etapa — nenhum cadastro de CNPJ existente
       passa a exigir um clique a mais).

       Desenho alternativo considerado e DESCARTADO: um passo de
       confirmação (duas telas, a segunda já com a opção pré-marcada).
       Resolveria igual, mas exigiria uma segunda tela inteira — com o
       próprio "o que foi digitado continua lá" do arquétipo B
       (direcao-de-arte.md §2.B) a garantir de novo — só para um campo
       opcional que uma linha de `clean()` já decide. Uma tela só, com a
       sugestão em `clean()`, é o desenho mais simples que ainda cumpre a
       HI-23 sem depender de script nenhum.
    """

    class Meta:
        model = Empresa
        fields = [
            "razao_social",
            "nome_fantasia",
            "tipo_inscricao",
            "cnpj",
            "cpf",
            "modo_escrituracao",
        ]
        help_texts = {
            "tipo_inscricao": (
                "CNPJ para pessoa jurídica; CPF para pessoa física (RC-112). "
                "Se não escolher, o sistema aplica CNPJ."
            ),
            "cnpj": "Aceita com ou sem máscara.",
            "cpf": "Aceita com ou sem máscara.",
            "modo_escrituracao": (
                "Se não escolher, o sistema aplica a sugestão: livro-caixa para "
                "CPF, contabilidade para CNPJ. Você pode trocar quando quiser."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # As duas opções ficam sempre visíveis (radio, não select oculto) —
        # ver o ponto 1 da docstring da classe. `choices=` explícito porque
        # trocar só o WIDGET (sem recriar o campo) não copia sozinho as
        # opções que o Django já tinha montado para o Select automático do
        # ModelForm.
        self.fields["tipo_inscricao"].widget = forms.RadioSelect(choices=TipoInscricao.choices)
        self.fields["modo_escrituracao"].widget = forms.RadioSelect(
            choices=ModoEscrituracao.choices
        )
        # `tipo_inscricao` em si é opcional na TELA (nenhuma opção vem
        # pré-marcada) — `clean()`, abaixo, aplica CNPJ quando ausente,
        # mesmo default do modelo (`TipoInscricao.CNPJ`).
        self.fields["tipo_inscricao"].required = False
        # HI-23 (ponto 4 da docstring da classe): nenhuma opção vem
        # pré-marcada — a AUSÊNCIA de escolha é o que aciona a sugestão em
        # `clean()`, nunca um valor fixo no widget.
        self.fields["modo_escrituracao"].required = False

        # ACHADO DE VERIFICAÇÃO VISUAL (Playwright, esta etapa): sem esta
        # linha, o formulário NOVO (GET, sem instância salva) renderizava
        # "CNPJ" e "Contabilidade" com o RADIO JÁ MARCADO — não por causa
        # de `required`/`initial` explícito nenhum, mas porque
        # `BaseModelForm.__init__` sempre semeia `self.initial` a partir
        # dos valores da instância em branco (`Empresa()`), e o `default=`
        # do MODELO já é `TipoInscricao.CNPJ`/`ModoEscrituracao.
        # CONTABILIDADE`. Isso não é só estético: um radio JÁ marcado é
        # ENVIADO pelo navegador mesmo que o contador nunca o toque — a
        # sugestão de HI-23 (livro-caixa para CPF) NUNCA seria acionada de
        # verdade por um usuário real, porque `modo_escrituracao` nunca
        # chegaria "ausente" ao servidor. `self.initial`, aqui, é o dict
        # que vence sobre o default do CAMPO na hora de decidir o que o
        # WIDGET desenha (`BoundField.value()` → `get_initial_for_field`);
        # zerar as DUAS chaves é o que faz o `<input>` nascer sem
        # `checked` em nenhuma das opções — a "ausência de escolha" que a
        # docstring da classe promete.
        self.initial["tipo_inscricao"] = None
        self.initial["modo_escrituracao"] = None

        # Ponto 3 da docstring da classe: `cnpj`/`cpf` são obrigatórios um
        # de cada vez, conforme o `tipo_inscricao` DESTE envio — lido do
        # dado BRUTO (`self.data`), porque `cleaned_data` só existe depois
        # de `_clean_fields()` rodar, e É a validação de CADA campo
        # (inclusive `required`) que `_clean_fields()` está prestes a
        # fazer. Um formulário NOVO, sem POST (`self.is_bound` falso), não
        # tem `self.data` — `getattr` com padrão vazio cobre os dois casos
        # sem `if`/`else` de bind.
        tipo_bruto = self.data.get("tipo_inscricao", "") if self.is_bound else ""
        if tipo_bruto == TipoInscricao.CPF:
            self.fields["cpf"].required = True
            self.fields["cnpj"].required = False
        else:
            # Ausente, inválido ou CNPJ: cai no mesmo lado que já existia
            # ANTES desta etapa (CNPJ obrigatório) — um valor de
            # `tipo_inscricao` que não seja nenhum dos dois válidos é
            # rejeitado por `ChoiceField.validate()` de qualquer forma; não
            # há necessidade de tratar esse caso aqui além de não travar.
            self.fields["cnpj"].required = True
            self.fields["cpf"].required = False

    def clean(self):
        cleaned = super().clean()

        # `tipo_inscricao` ausente vira CNPJ — mesmo padrão do modelo
        # (`TipoInscricao.CNPJ` é o `default=` de `Empresa.tipo_inscricao`)
        # e o único comportamento que existia antes desta etapa. Sem esta
        # linha, um POST que não marque nenhuma opção deixaria
        # `cleaned_data["tipo_inscricao"] = ""` — valor que
        # `construct_instance` (chamado por `_post_clean()`, DEPOIS deste
        # método) gravaria por cima do default do modelo, e "" não é CNPJ
        # nem CPF (violaria "empresa_inscricao_consistente_com_tipo" na
        # gravação, com a mensagem GENÉRICA do Django em vez das
        # específicas abaixo).
        tipo = cleaned.get("tipo_inscricao") or TipoInscricao.CNPJ
        cleaned["tipo_inscricao"] = tipo
        cnpj = cleaned.get("cnpj") or ""
        cpf = cleaned.get("cpf") or ""

        # A obrigatoriedade "campo vazio" de cnpj/cpf já foi decidida em
        # `__init__` (mensagem padrão do Django, preservando o texto que
        # já existia antes desta etapa). Aqui só falta a OUTRA metade da
        # regra cruzada — MESMA mensagem de `EmpresaSerializer.validate`
        # (apps/empresas/serializers.py), DE-026 — o campo do tipo ERRADO
        # também preenchido. `cnpj`/`cpf` só chegam aqui truthy quando o
        # campo em si já passou pela limpeza sem erro (um valor que
        # estourou em `to_python` nunca entra em `cleaned_data`), então
        # este `if` nunca duplica um erro já reportado por outro caminho.
        if tipo == TipoInscricao.CPF and cnpj:
            self.add_error("cnpj", "CNPJ não pode ser informado quando o tipo de inscrição é CPF.")
        elif tipo == TipoInscricao.CNPJ and cpf:
            self.add_error("cpf", "CPF não pode ser informado quando o tipo de inscrição é CNPJ.")

        # HI-23 — sugestão sem JavaScript (ver o ponto 4 da docstring da
        # classe). Só entra em jogo quando o contador NÃO marcou nenhuma
        # opção; qualquer escolha explícita — mesmo igual à sugestão —
        # chega aqui já preenchida em `cleaned` e não é sobrescrita.
        # Mutar `cleaned` (e devolvê-lo) é o que propaga o valor para
        # `self.instance` mais adiante: `BaseModelForm._post_clean()`
        # constrói a instância a partir de `self.cleaned_data` (que passa
        # a ser este `cleaned`, por `_clean_form()`) DEPOIS deste método
        # retornar — não precisamos tocar `self.instance` aqui.
        if not cleaned.get("modo_escrituracao"):
            cleaned["modo_escrituracao"] = (
                ModoEscrituracao.LIVRO_CAIXA
                if tipo == TipoInscricao.CPF
                else ModoEscrituracao.CONTABILIDADE
            )

        return cleaned
