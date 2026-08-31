#!/usr/bin/env python3
"""Como um card é escrito e como é lido de volta.

O card tem que servir aos dois lados: você lê a descrição e entende na hora; o
robô lê o mesmo texto e recupera os dados exatos (u/i/e, dependências, origem).

A solução é um rodapé em bloco de código no fim da descrição. O Trello renderiza
como um bloquinho cinza discreto, e o robô acha por marcador. Sem depender de
Power-Up pago (Custom Fields), então funciona em qualquer plano do Trello.

Formato do nome do card:   #A1 — G7 autorizar o piloto de 10 anúncios
O #ID é o que amarra tudo: você cita "#A1" numa conversa qualquer e a skill
`task` (já existente) acha o contexto inteiro. O ID sobrevive à mudança de nome.
"""
import json
import re

MARCADOR = "quadro-dados"
_BLOCO = re.compile(r"```" + MARCADOR + r"\s*\n(.*?)\n```", re.S)
_ID_NO_NOME = re.compile(r"^#([A-Z]\d+)\s*[—\-–]\s*(.*)$")

_FAIXA_HUMANA = {
    "agora":   "AGORA — hoje, só o que ninguém pode fazer por você",
    "relogio": "O RELÓGIO — tem prazo de terceiro",
    "semana":  "O GATE — a obra da semana",
    "depois":  "DEPOIS — destravado pelo gate",
    "fila":    "FILA FRIA — congelado por desenho",
}
_STATUS_HUMANO = {
    "voce": "trava em você", "terceiro": "espera terceiro", "risco": "pode virar crítico",
    "fila": "congelado", "pronto": "pronto",
}


def nome_do_card(task_id, titulo):
    """#A1 — título. Sem ID (trabalho capturado do worklog), só o título."""
    titulo = " ".join((titulo or "").split())
    if not titulo:
        titulo = "trabalho sem título"
    nome = f"#{task_id} — {titulo}" if task_id else titulo
    return nome[:16384]


def id_do_nome(nome):
    m = _ID_NO_NOME.match((nome or "").strip())
    return m.group(1) if m else None


def montar_desc(dados, corpo=""):
    """Monta a descrição: o texto humano em cima, o rodapé de máquina embaixo."""
    partes = []
    if corpo:
        partes.append(corpo.rstrip())

    linha = []
    if dados.get("faixa"):
        linha.append(_FAIXA_HUMANA.get(dados["faixa"], dados["faixa"]))
    if dados.get("status"):
        linha.append(_STATUS_HUMANO.get(dados["status"], dados["status"]))
    if linha:
        partes.append("**" + " · ".join(linha) + "**")

    if any(dados.get(k) is not None for k in ("u", "i", "e")):
        partes.append(
            f"urgência **{dados.get('u', '?')}** · impacto **{dados.get('i', '?')}** · "
            f"esforço **{dados.get('e', '?')}** · peso **{dados.get('peso', '?')}**")

    if dados.get("dep"):
        partes.append("depende de: " + " ".join(f"#{d}" for d in dados["dep"]))

    if dados.get("fonte"):
        partes.append(f"_fonte:_ {dados['fonte']}")

    if dados.get("motivo"):
        partes.append(f"_como caiu aqui:_ {dados['motivo']}")

    limpo = {k: v for k, v in dados.items() if v is not None and k != "corpo"}
    partes.append(f"```{MARCADOR}\n{json.dumps(limpo, ensure_ascii=False, sort_keys=True)}\n```")
    return "\n\n".join(partes)[:16384]


def ler_desc(desc):
    """Recupera o rodapé de máquina. Card mexido na mão sem rodapé devolve {}."""
    m = _BLOCO.search(desc or "")
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except Exception:
        return {}


def trocar_dados(desc, novos):
    """Reescreve só o rodapé, preservando tudo que a pessoa escreveu no card."""
    bloco = f"```{MARCADOR}\n{json.dumps(novos, ensure_ascii=False, sort_keys=True)}\n```"
    if _BLOCO.search(desc or ""):
        return _BLOCO.sub(lambda _: bloco, desc, count=1)
    return ((desc or "").rstrip() + "\n\n" + bloco).strip()


if __name__ == "__main__":
    d = {"id": "A1", "area": "A", "faixa": "semana", "status": "voce",
         "u": 5, "i": 5, "e": 2, "peso": 10, "dep": ["A2"], "origem": "quadro",
         "tipo": "obra", "fonte": "~/mercador/LIVRO-DE-OBRA.md linha 62"}
    desc = montar_desc(d, "Gate humano aberto desde 20/08. Nada foi ao ar.")
    print(desc)
    print("\n--- volta ---")
    volta = ler_desc(desc)
    assert volta == d, f"ida e volta quebrou:\n{volta}\n{d}"
    print("✅ ida e volta preserva os dados")

    nome = nome_do_card("A1", "G7 — autorizar o piloto de 10 anúncios")
    assert id_do_nome(nome) == "A1", nome
    assert id_do_nome("card escrito na mão pelo Davi") is None
    print(f"✅ nome: {nome}  → id recuperado: {id_do_nome(nome)}")

    # o que a pessoa escreve no card não pode ser comido pelo robô
    mexido = desc.replace("Gate humano", "MUDEI ISSO NA MÃO. Gate humano")
    novo = trocar_dados(mexido, {**d, "status": "pronto"})
    assert "MUDEI ISSO NA MÃO" in novo, "o robô comeu o texto do dono"
    assert ler_desc(novo)["status"] == "pronto"
    print("✅ o robô troca o rodapé sem comer o que você escreveu")
