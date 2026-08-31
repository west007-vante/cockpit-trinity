#!/usr/bin/env python3
"""Levanta O QUADRO no Trello — board, listas, etiquetas e convites. Roda 1×.

Idempotente de propósito: rodar de novo não duplica nada. Ele confere o que já
existe, cria só o que falta, e no fim grava o TRELLO_BOARD_ID no ~/.steve/trello.env.

Uso:
    python3 bootstrap_board.py                    # cria/conserta o quadro
    python3 bootstrap_board.py --conferir         # só mostra o que faria, não mexe
    python3 bootstrap_board.py --convidar davi@x.com,steve@x.com,rico@x.com

Convite ≠ criar conta. Quem aceita o convite é a pessoa, na caixa dela.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trello_api import Trello, TrelloErro, ENV_FILE   # noqa: E402

NOME_DO_QUADRO = "O QUADRO · Pyerri × Davi"
DESC_DO_QUADRO = (
    "Quadro vivo de Pyerri, Davi, Steve e Rico.\n\n"
    "A coluna diz o ESTADO. O membro diz QUEM. A etiqueta diz a FRENTE.\n"
    "Cards com #ID vêm do Quadro da Obra — cite o ID em qualquer conversa "
    "com o Steve e ele acha o contexto inteiro.\n\n"
    "Alimentado sozinho pelas sessões do Claude Code. Conversa fiada não vira card.")

# A ordem é a ordem em que elas aparecem no quadro, da esquerda pra direita.
LISTAS = [
    ("📥 Entrada",    "o robô capturou mas não soube classificar — você tria"),
    ("📋 Tarefas",    "a fila: existe, está desenhado, não é pra hoje"),
    ("🗓️ Hoje",       "agendado pra hoje"),
    ("🔨 Fazendo",    "em execução agora"),
    ("⏸️ Parado",     "travado esperando alguém ou alguma coisa"),
    ("🕐 Adiado",     "volta numa data futura"),
    ("✅ Feito",      "fechado"),
    ("🗑️ Descartado", "morreu por decisão"),
    ("👥 Clientes",   "um card por cliente"),
    ("🧪 Bancada",    "curiosidade, hobby, experimento"),
]

# 9 áreas do Quadro da Obra + 3 tipos. Cores fixas pra bater o olho e saber.
ETIQUETAS = [
    ("A · MERCADOR",  "yellow"),
    ("B · Shopee",    "orange"),
    ("C · GF Cortes", "red"),
    ("D · VERSO",     "purple"),
    ("E · Tikebum",   "blue"),
    ("F · Zero→Venda", "sky"),
    ("G · Infra",     "lime"),
    ("H · Entrega",   "pink"),
    ("I · Comercial", "black"),
    ("🔨 obra",       "green_dark"),
    ("🎯 cliente",    "red_dark"),
    ("🧪 bancada",    "purple_dark"),
]


def gravar_env(chave, valor, arquivo=ENV_FILE):
    """Grava/atualiza uma linha do .env sem clobberar o resto (mesmo cuidado do install_worklog)."""
    linhas, achou = [], False
    if os.path.exists(arquivo):
        linhas = open(arquivo, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(linhas):
        if ln.strip().startswith(chave + "="):
            linhas[i] = f"{chave}={valor}"
            achou = True
            break
    if not achou:
        linhas.append(f"{chave}={valor}")
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    os.chmod(arquivo, 0o600)       # token é segredo — só o dono lê


def achar_board(t):
    """Reencontra o quadro pelo nome, pra rodar de novo não criar um segundo."""
    if t.board_id:
        try:
            return t.board()
        except TrelloErro:
            pass
    for b in (t.get("/members/me/boards", fields="id,name,url,shortUrl,closed") or []):
        if b.get("name") == NOME_DO_QUADRO and not b.get("closed"):
            return b
    return None


def main():
    conferir = "--conferir" in sys.argv
    convidar = []
    for i, a in enumerate(sys.argv):
        if a == "--convidar" and i + 1 < len(sys.argv):
            convidar = [e.strip() for e in sys.argv[i + 1].split(",") if e.strip()]

    t = Trello()
    eu = t.eu()
    print(f"conectado como {eu.get('fullName')} (@{eu.get('username')})")
    if conferir:
        print("MODO CONFERÊNCIA — nada será criado.\n")

    # ------------------------------------------------------------------- o board
    b = achar_board(t)
    if b:
        print(f"✅ quadro já existe: {b['name']} → {b.get('shortUrl') or b.get('url')}")
    elif conferir:
        print(f"➕ criaria o quadro: {NOME_DO_QUADRO}")
        return
    else:
        b = t.criar_board(NOME_DO_QUADRO, desc=DESC_DO_QUADRO)
        print(f"➕ quadro criado: {b.get('shortUrl') or b.get('url')}")
    board_id = b["id"]
    t.board_id = board_id

    # ------------------------------------------------------------------ as listas
    existentes = {l["name"]: l for l in t.listas(board_id)}
    for pos, (nome, _oque) in enumerate(LISTAS, start=1):
        if nome in existentes:
            print(f"   ✔ lista já existe: {nome}")
        elif conferir:
            print(f"   ➕ criaria a lista: {nome}")
        else:
            t.criar_lista(nome, pos * 1000, board_id)
            print(f"   ➕ lista criada: {nome}")

    # ------------------------------------------------- listas que não são nossas
    # Quadro criado na mão pela interface nasce com "To Do / Doing / Done". Elas
    # ficam sobrando. Só arquivamos se estiverem VAZIAS e só com --limpar: lista
    # com card dentro é trabalho de alguém, e isso não se apaga por conta própria.
    nossas = {n for n, _ in LISTAS}
    for l in t.listas(board_id):
        if l["name"] in nossas:
            continue
        try:
            n_cards = len(t.cards_da_lista(l["id"]) or [])
        except TrelloErro:
            n_cards = -1
        if n_cards == 0 and "--limpar" in sys.argv and not conferir:
            t.put(f"/lists/{l['id']}/closed", value="true")
            print(f"   🗑️  lista vazia arquivada: {l['name']}")
        elif n_cards == 0:
            print(f"   ↩︎  lista sobrando (vazia): {l['name']}  — some com --limpar")
        else:
            print(f"   ⚠️  lista sobrando com {n_cards} card(s): {l['name']} — deixei quieta")

    # --------------------------------------------------------------- as etiquetas
    ja = {(e.get("name") or "") for e in (t.etiquetas(board_id) or [])}
    for nome, cor in ETIQUETAS:
        if nome in ja:
            print(f"   ✔ etiqueta já existe: {nome}")
        elif conferir:
            print(f"   ➕ criaria a etiqueta: {nome} ({cor})")
        else:
            t.criar_etiqueta(nome, cor, board_id)
            print(f"   ➕ etiqueta criada: {nome} ({cor})")

    # ---------------------------------------------------------------- os convites
    if convidar:
        atuais = {m.get("username") for m in (t.membros(board_id) or [])}
        print(f"   membros hoje: {', '.join(sorted(x for x in atuais if x)) or '(só você)'}")
        for email in convidar:
            if conferir:
                print(f"   ➕ convidaria: {email}")
                continue
            try:
                t.convidar_por_email(email, board_id=board_id)
                print(f"   ✉️  convite enviado: {email}")
            except TrelloErro as e:
                print(f"   ⚠️  não deu pra convidar {email}: {e}")

    # -------------------------------------------------------------------- gravar
    if not conferir:
        gravar_env("TRELLO_BOARD_ID", board_id)
        print(f"\n✅ TRELLO_BOARD_ID gravado em {ENV_FILE}")
        print(f"   o quadro: {b.get('shortUrl') or b.get('url')}")
        print("\npróximo passo:  python3 ~/trinity/trello/migrar_quadro.py --conferir")


if __name__ == "__main__":
    try:
        main()
    except TrelloErro as e:
        print(f"❌ {e}")
        sys.exit(1)
