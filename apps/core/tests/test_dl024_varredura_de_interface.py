"""Varredura de interface — o mecanismo que transforma a direção de arte em
regra, e não em pedido.

**Por que este arquivo existe.** A [direção de arte](docs/projeto/direcao-de-arte.md)
foi escolhida por medição, num gauntlet de três variantes (DE-042/RC-89). Mas o
produto vai ganhar Fiscal, Folha, Honorários, Paralegal e Lalur, e **um sistema
contábil que muda de cara a cada módulo obriga o usuário a reaprender a ler**.
Documento de padrão que ninguém verifica vira decoração em seis meses — este
projeto já viu isso acontecer com o estado, que precisou de
``test_documentacao_do_estado.py`` para parar de divergir.

**O que esta varredura NÃO faz, e é importante dizer.** Ela é estática: lê
template e folha de estilo. Ela **não** renderiza, não mede contraste, não mede
densidade e não sabe se a tela é bonita. O que se mede em navegador está no
juiz do gauntlet (``docs/assets/design/gauntlet/juiz.py``), que roda fora da
integração contínua porque exige Chromium. Aqui ficam só as regras que dá para
provar lendo o arquivo — e cada uma delas nasceu de um defeito real.

**Cada guarda tem controle positivo.** O projeto aprendeu na marra (BL-271) que
teste que não morre quando a defesa é removida não é guarda, é enfeite: um
teste da DL-023 comparava dois literais entre si e passaria igual com o defeito
de volta. Por isso, aqui, cada detector é exercitado contra uma entrada
propositalmente inválida no mesmo arquivo.
"""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
TEMPLATES = RAIZ / "templates"
ESTILOS = RAIZ / "static" / "css"
DIRECAO_DE_ARTE = RAIZ / "docs" / "projeto" / "direcao-de-arte.md"

# Pastas de `templates/` que NÃO são módulo de negócio e por isso não precisam
# de linha na tabela do "momento da verdade". Cada uma com o motivo escrito: a
# lição da DL-023 é que superfície sem decisão registrada é o defeito, e
# "estava lá antes" não é decisão.
PASTAS_QUE_NAO_SAO_MODULO = {
    "erros": "páginas de erro do próprio sistema, sem documento de negócio",
    "registration": "entrada no sistema (login), fornecida pelo Django",
    "tenancy": "escritório e vínculo de usuário: infraestrutura de isolamento",
    "empresas": "cadastro central compartilhado, não é módulo de rotina",
}

# Convenção do projeto: valor formatado em pt-BR chega ao template com sufixo
# `_ptbr`. Nem todo `_ptbr` é dinheiro — data também usa —, por isso a regra
# vale dentro de CÉLULA DE TABELA, que é onde a coluna de valor mora.
PADRAO_VALOR = re.compile(r"\{\{[^}]*_ptbr[^}]*\}\}")
PADRAO_CELULA = re.compile(r"<(td|th)\b[^>]*>", re.IGNORECASE)
PADRAO_COR = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\([^)]*\)|\bhsla?\([^)]*\)")


def _templates():
    return sorted(TEMPLATES.rglob("*.html"))


def _e_parcial(caminho):
    """Trecho reaproveitado (`_nome.html`) não estende moldura: ele é incluído."""
    return caminho.name.startswith("_")


def _sem_comentarios_css(texto):
    return re.sub(r"/\*.*?\*/", "", texto, flags=re.S)


def _cores_fora_dos_tokens(texto):
    """Cores declaradas fora do bloco `:root`.

    O `:root` é onde os tokens moram (DE-042). Cor escrita direto numa regra de
    tela é o começo da divergência: a próxima tela copia, a terceira erra o
    tom, e seis meses depois existem quatro azuis.
    """
    limpo = _sem_comentarios_css(texto)
    for bloco in re.finditer(r":root\s*\{.*?\}", limpo, flags=re.S):
        limpo = limpo.replace(bloco.group(0), "")
    return PADRAO_COR.findall(limpo)


def _valores_sem_classe(texto):
    """Valores `_ptbr` dentro de célula de tabela que não usam a classe do
    sistema. Devolve a lista dos trechos ofensores."""
    ofensores = []
    for valor in PADRAO_VALOR.finditer(texto):
        anteriores = list(PADRAO_CELULA.finditer(texto, 0, valor.start()))
        if not anteriores:
            continue  # o valor não está dentro de célula: fora do alcance da regra
        celula = anteriores[-1]
        # A célula só vale se o valor estiver antes do próximo fechamento dela.
        fechamento = texto.find(f"</{celula.group(1)}>", celula.end())
        if fechamento != -1 and fechamento < valor.start():
            continue
        if "valor-monetario" not in celula.group(0):
            ofensores.append((celula.group(0)[:70], valor.group(0)[:40]))
    return ofensores


def _cabecalhos_sem_escopo(texto):
    achados = re.finditer(r"<th\b[^>]*>", texto)
    return [m.group(0)[:70] for m in achados if "scope=" not in m.group(0)]


# As duas dívidas que este bloco registrava (DIVIDA_VALOR: 4 células de
# totalizador fora da classe do sistema em lancamento_form.html e razao.html;
# DIVIDA_COR: 5 cores soltas em static/css/base.css) foram FECHADAS pela
# implementação real da DL-024 (DE-042) nesta etapa — `strict=True` fez
# exatamente o que o comentário original previa: "no instante em que a
# implementação consertar, o teste passa a REPROVAR POR PASSAR, e quem
# estiver aqui é obrigado a apagar a marca". As duas marcas de
# `xfail` saíram das guardas abaixo; elas agora correm como guarda normal,
# sem rede de segurança para a dívida — porque a dívida não existe mais.

# ---------------------------------------------------------------------------
# As guardas
# ---------------------------------------------------------------------------


def test_toda_tela_estende_a_moldura_comum():
    """Tela que não estende `base.html` nasce fora do sistema visual.

    É assim que um módulo novo começa a divergir: alguém copia um HTML inteiro
    "só para testar" e ele fica. A moldura carrega marca, contexto de empresa e
    competência, navegação e os tokens — sair dela é sair da direção de arte.
    """
    fora = [
        str(t.relative_to(RAIZ))
        for t in _templates()
        if t.name != "base.html"
        and not _e_parcial(t)
        and "{% extends" not in t.read_text(encoding="utf-8")
    ]
    assert not fora, (
        "Telas que não estendem a moldura comum: "
        + ", ".join(fora)
        + ". Trecho reaproveitado começa com '_'; tela estende base.html."
    )


def test_toda_tabela_declara_legenda():
    """`<caption>` é o que diz ao leitor de tela o que a tabela contém.

    Sem ela, quem usa leitor de tela cai numa grade de números sem saber se está
    no Balancete ou no Razão. É requisito da própria W3C para tabela de dados, e
    o projeto já a tem em todas — esta guarda impede o próximo módulo de chegar
    sem.
    """
    faltando = []
    for t in _templates():
        texto = t.read_text(encoding="utf-8")
        tabelas = len(re.findall(r"<table\b", texto, re.IGNORECASE))
        legendas = len(re.findall(r"<caption\b", texto, re.IGNORECASE))
        if tabelas > legendas:
            faltando.append(f"{t.relative_to(RAIZ)} ({tabelas} tabelas, {legendas} legendas)")
    assert not faltando, "Tabelas sem <caption>: " + "; ".join(faltando)


def test_todo_cabecalho_de_tabela_declara_escopo():
    """`<th>` sem `scope` faz o leitor de tela ler "1.234,56" sem dizer de qual
    coluna e de qual conta. Em tabela contábil, é o mesmo que não ler nada."""
    faltando = []
    for t in _templates():
        for cabecalho in _cabecalhos_sem_escopo(t.read_text(encoding="utf-8")):
            faltando.append(f"{t.relative_to(RAIZ)}: {cabecalho}")
    assert not faltando, "Cabeçalhos de tabela sem scope: " + "; ".join(faltando)


def test_todo_valor_em_celula_usa_a_classe_do_sistema():
    """Coluna de valor sem a classe do sistema perde a tabulação de algarismos.

    O efeito é o que o gauntlet mediu e nomeou: as colunas **dançam**, porque
    `1` e `8` têm larguras diferentes em fonte proporcional, e o olho perde a
    referência vertical justamente onde a conferência acontece.
    """
    ofensores = []
    for t in _templates():
        for celula, valor in _valores_sem_classe(t.read_text(encoding="utf-8")):
            ofensores.append(f"{t.relative_to(RAIZ)}: {valor} em {celula}")
    assert not ofensores, (
        "Valores em célula de tabela sem a classe 'valor-monetario': " + "; ".join(ofensores)
    )


def test_a_classe_de_valor_tabula_algarismos():
    """A classe existe — mas ela precisa **fazer** o que promete.

    Guarda contra o defeito exato da BL-271: o nome certo no lugar certo, e a
    propriedade que importa removida sem ninguém perceber.
    """
    css = (ESTILOS / "base.css").read_text(encoding="utf-8")
    bloco = re.search(r"\.valor-monetario\s*\{(.*?)\}", css, flags=re.S)
    assert bloco, "A classe .valor-monetario sumiu de static/css/base.css"
    corpo = bloco.group(1)
    assert "tabular-nums" in corpo or "mono" in corpo.lower(), (
        "A classe .valor-monetario existe mas não tabula algarismos. "
        "Sem isso as colunas de valor voltam a dançar: " + corpo.strip()[:120]
    )


def test_nenhuma_cor_declarada_fora_dos_tokens():
    """Cor solta é o começo de quatro azuis diferentes (DE-042)."""
    soltas = []
    for folha in sorted(ESTILOS.glob("*.css")):
        for cor in _cores_fora_dos_tokens(folha.read_text(encoding="utf-8")):
            soltas.append(f"{folha.relative_to(RAIZ)}: {cor}")
    assert not soltas, (
        "Cores declaradas fora do :root (tokens da DE-042): "
        + "; ".join(soltas)
        + ". Se a cor é nova, ela nasce como token com o contraste medido."
    )


def test_nenhum_estilo_embutido_no_template():
    """`style="..."` no template escapa do sistema de tokens e da auditoria de
    contraste: ninguém encontra aquele valor depois."""
    embutidos = []
    for t in _templates():
        for m in re.finditer(r'style="[^"]+"', t.read_text(encoding="utf-8")):
            embutidos.append(f"{t.relative_to(RAIZ)}: {m.group(0)[:60]}")
    assert not embutidos, "Estilo embutido em template: " + "; ".join(embutidos)


def test_modulo_novo_declara_o_seu_momento_da_verdade():
    """Módulo sem a sua pergunta escrita não devia ter tela desenhada.

    O "momento da verdade" é a pergunta que a tela responde **antes de gravar**
    — no Contábil, "débito é igual a crédito?". Quem não sabe responder pelo
    Fiscal, pela Folha ou pelo Lalur tem um problema de entendimento do
    domínio, e a hora de descobrir é antes da tela, não depois.
    """
    texto = DIRECAO_DE_ARTE.read_text(encoding="utf-8").lower()
    sem_linha = []
    for pasta in sorted(p for p in TEMPLATES.iterdir() if p.is_dir()):
        nome = pasta.name
        if nome in PASTAS_QUE_NAO_SAO_MODULO:
            continue
        chave = {"contabilidade": "contábil"}.get(nome, nome)
        if chave not in texto:
            sem_linha.append(nome)
    assert not sem_linha, (
        "Módulos com tela mas sem linha na tabela do 'momento da verdade' de "
        f"docs/projeto/direcao-de-arte.md: {', '.join(sem_linha)}. "
        "Escreva a pergunta que a tela responde antes de gravar — ou declare a "
        "pasta em PASTAS_QUE_NAO_SAO_MODULO, com o motivo."
    )


# ---------------------------------------------------------------------------
# Controles positivos: cada detector precisa saber reprovar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "css_ruim, esperado",
    [
        (":root { --a: #fff; }\n.botao { color: #123456; }", "#123456"),
        (":root { --a: #fff; }\n.aviso { background: rgb(1, 2, 3); }", "rgb(1, 2, 3)"),
    ],
)
def test_controle_positivo_detector_de_cor_solta(css_ruim, esperado):
    assert esperado in _cores_fora_dos_tokens(css_ruim)


def test_controle_positivo_detector_de_cor_ignora_o_que_esta_no_token():
    assert _cores_fora_dos_tokens(":root {\n  --cor-texto: #1a1a1a;\n}\n") == []


def test_controle_positivo_detector_de_valor_sem_classe():
    ruim = '<table><tr><td class="numero">{{ linha.saldo_ptbr }}</td></tr></table>'
    bom = '<table><tr><td class="valor-monetario">{{ linha.saldo_ptbr }}</td></tr></table>'
    fora_de_tabela = '<p class="texto-apoio">{{ data_minima_ptbr }}</p>'
    assert _valores_sem_classe(ruim), "o detector deixou passar valor sem a classe"
    assert not _valores_sem_classe(bom)
    assert not _valores_sem_classe(fora_de_tabela), (
        "data em prosa não é coluna de valor; a regra vale dentro de célula de tabela"
    )


def test_controle_positivo_detector_de_escopo():
    assert _cabecalhos_sem_escopo("<th>Conta</th>")
    assert not _cabecalhos_sem_escopo('<th scope="col">Conta</th>')
