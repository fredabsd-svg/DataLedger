import csv
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PARIDADE = RAIZ / "docs" / "projeto" / "paridade"
SAIDA = RAIZ.parent / "planilha-do-que-falta.csv"

MODULOS = [
    ("contabilidade.md", "Contabilidade"),
    ("fiscal.md", "Fiscal"),
    ("folha.md", "Folha"),
    ("honorarios.md", "Honorarios"),
    ("patrimonio.md", "Patrimonio"),
    ("lalur.md", "Lalur"),
]

RE_ITEM = re.compile(r"^###\s+([A-Z]{3,4}-\d+)\s*[-—]\s*(.+?)\s*$")
RE_SITUACAO = re.compile(r"\*\*Situa..o no DataLedger\.\*\*", re.IGNORECASE)
RE_DEPENDE = re.compile(r"\*\*Depende de\.\*\*", re.IGNORECASE)
RE_SECAO = re.compile(r"^##\s+.*(fora de escopo|obsoleto)", re.IGNORECASE)

# Ordem obrigatoria: "existe" e substring de "nao existe", entao o negativo
# vem primeiro. Invertido, tudo vira "existe" (aconteceu na 1a execucao).
CATEGORIAS = [
    ("não existe", "nao existe"),
    ("nao existe", "nao existe"),
    ("parcial", "parcial"),
    ("pronto e auditado", "existe"),
    ("pronto", "existe"),
    ("coberto pela infraestrutura", "existe"),
    ("existe", "existe"),
]


def classificar(texto):
    baixo = texto.lower()
    for marca, rotulo in CATEGORIAS:
        if marca in baixo:
            return rotulo
    return "sem situacao declarada"


def ler_campo(linhas, padrao):
    # Le a linha do campo e as continuacoes, parando na linha em branco. Ler
    # ate o proximo campo arrastava texto de outros: em CTB-01 a situacao e
    # "Existe" e, 20 linhas depois, uma regra traz "Nao existe"; o
    # classificador via o texto errado e marcava como lacuna algo que existe
    # em producao.
    partes = []
    achou = False
    for linha in linhas:
        if not achou:
            if padrao.search(linha):
                achou = True
                partes.append(padrao.split(linha, 1)[1])
            continue
        if not linha.strip():
            break
        partes.append(linha)
    if not achou:
        return ""
    return " ".join(p.strip() for p in partes if p.strip()).strip()


def main():
    linhas_csv = []
    contagem = {}
    contagem_fora = {}

    for arquivo, modulo in MODULOS:
        caminho = PARIDADE / arquivo
        if not caminho.exists():
            print("AVISO: falta " + str(caminho), file=sys.stderr)
            continue
        texto = caminho.read_text(encoding="utf-8").splitlines()

        inicio_fora = len(texto)
        for indice, linha in enumerate(texto):
            if RE_SECAO.match(linha):
                inicio_fora = indice
                break

        itens = []
        atual = None
        for indice, linha in enumerate(texto):
            achou = RE_ITEM.match(linha)
            if achou:
                if atual:
                    itens.append(atual)
                atual = {
                    "id": achou.group(1),
                    "nome": achou.group(2).strip(),
                    "linha": indice,
                    "fora": indice >= inicio_fora,
                }
            elif atual is not None and linha.startswith("## "):
                itens.append(atual)
                atual = None
        if atual:
            itens.append(atual)

        for posicao, item in enumerate(itens):
            fim = itens[posicao + 1]["linha"] if posicao + 1 < len(itens) else len(texto)
            bloco = texto[item["linha"] : fim]
            situacao_texto = ler_campo(bloco, RE_SITUACAO)
            depende = ler_campo(bloco, RE_DEPENDE)
            cat = "sem situacao declarada" if not situacao_texto else classificar(situacao_texto)
            contagem[(modulo, cat)] = contagem.get((modulo, cat), 0) + 1
            contagem_fora[modulo] = contagem_fora.get(modulo, 0) + (1 if item["fora"] else 0)
            linhas_csv.append(
                {
                    "id": item["id"],
                    "modulo": modulo,
                    "item": item["nome"],
                    "situacao": cat,
                    "secao_fora_de_escopo": "sim" if item["fora"] else "nao",
                    "depende_de": depende[:160] or "-",
                }
            )

    colunas = ["id", "modulo", "item", "situacao", "secao_fora_de_escopo", "depende_de"]
    with SAIDA.open("w", encoding="utf-8-sig", newline="") as saida:
        escritor = csv.DictWriter(saida, fieldnames=colunas)
        escritor.writeheader()
        escritor.writerows(linhas_csv)

    print(str(len(linhas_csv)) + " itens em " + str(SAIDA))
    print()
    print("modulo          existe  parcial  naoexiste  semsit  total  emfora")
    for _, modulo in MODULOS:
        e = contagem.get((modulo, "existe"), 0)
        p = contagem.get((modulo, "parcial"), 0)
        n = contagem.get((modulo, "nao existe"), 0)
        s = contagem.get((modulo, "sem situacao declarada"), 0)
        f = contagem_fora.get(modulo, 0)
        print("%-14s %6d %8d %10d %7d %6d %7d" % (modulo, e, p, n, s, e + p + n + s, f))
    gerais = {}
    for (_, cat), qtd in contagem.items():
        gerais[cat] = gerais.get(cat, 0) + qtd
    print()
    print("TOTAL:", gerais)


if __name__ == "__main__":
    main()
