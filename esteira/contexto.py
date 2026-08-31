#!/usr/bin/env python3
"""O CONTEXTO — o que o agente sabe antes de começar a tarefa.

Quatro fontes plugáveis no nó, cada uma virando um pedaço do "pacote":

  {"tipo":"pasta",   "caminho":"~/mercador"}                 mapa + arquivos pequenos
  {"tipo":"cofre",   "caminho":"~/Downloads/cerebro-obsidian",
                     "busca":"anúncio mercado livre"}        busca nos .md do Obsidian
  {"tipo":"card",    "id":"A1"}                              o cartão do quadro como briefing
  {"tipo":"arquivo", "caminho":"~/plano.md"}                 conteúdo direto

O pacote tem TETO — contexto sem teto vira fatura (nuvem) ou estouro (local).
Cada fonte declara de onde veio, pro agente poder citar a origem.
"""
import os
import re
import sys
import unicodedata

TETO_PADRAO = 24000          # ~6k tokens de contexto — generoso sem ser gastador
TETO_POR_FONTE = 9000


def _simples(t):
    t = unicodedata.normalize("NFD", (t or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _ler(caminho, teto):
    try:
        with open(caminho, encoding="utf-8", errors="ignore") as f:
            return f.read(teto)
    except Exception as e:
        return f"(não consegui ler: {e})"


def de_pasta(caminho, teto=TETO_POR_FONTE):
    raiz = os.path.expanduser(caminho)
    if not os.path.isdir(raiz):
        return f"(a pasta {caminho} não existe)"
    linhas, lidos, gasto = [], [], 0
    for base, dirs, arqs in os.walk(raiz):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"][:12]
        nivel = base[len(raiz):].count(os.sep)
        if nivel > 2:
            dirs[:] = []
            continue
        rel = os.path.relpath(base, raiz)
        linhas.append(("  " * nivel) + (rel if rel != "." else "./"))
        for a in sorted(arqs)[:20]:
            linhas.append(("  " * nivel) + "  " + a)
            # arquivos de texto pequenos entram inteiros no pacote
            if gasto < teto // 2 and a.lower().endswith((".md", ".txt")) :
                p = os.path.join(base, a)
                try:
                    if os.path.getsize(p) < 4000:
                        corpo = _ler(p, 3800)
                        lidos.append(f"--- {os.path.relpath(p, raiz)} ---\n{corpo}")
                        gasto += len(corpo)
                except Exception:
                    pass
        if len(linhas) > 120:
            linhas.append("… (mapa cortado)")
            break
    out = "MAPA:\n" + "\n".join(linhas[:130])
    if lidos:
        out += "\n\nARQUIVOS PEQUENOS:\n" + "\n\n".join(lidos)
    return out[:teto]


def de_cofre(caminho, busca, teto=TETO_POR_FONTE):
    """Busca burra e honesta nos .md do cofre: conta ocorrência dos termos,
    devolve os trechos dos mais relevantes. Sem embedding, sem índice — a
    primeira versão que funciona; se um dia doer, evolui."""
    raiz = os.path.expanduser(caminho)
    if not os.path.isdir(raiz):
        return f"(o cofre {caminho} não existe)"
    termos = [_simples(t) for t in re.findall(r"\w{3,}", busca or "") ][:8]
    if not termos:
        return "(busca vazia — diga o que procurar no cofre)"
    placar = []
    for base, dirs, arqs in os.walk(raiz):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for a in arqs:
            if not a.endswith(".md"):
                continue
            p = os.path.join(base, a)
            try:
                corpo = _ler(p, 40000)
            except Exception:
                continue
            cs = _simples(corpo)
            pts = sum(cs.count(t) for t in termos)
            if pts:
                placar.append((pts, p, corpo))
    if not placar:
        return f"(nada no cofre casou com: {busca})"
    placar.sort(key=lambda x: -x[0])
    partes, gasto = [], 0
    for pts, p, corpo in placar[:4]:
        rel = os.path.relpath(p, raiz)
        # o trecho em volta da primeira ocorrência do termo mais forte
        cs = _simples(corpo)
        pos = min((cs.find(t) for t in termos if cs.find(t) >= 0), default=0)
        ini = max(0, pos - 300)
        trecho = corpo[ini:ini + 2200]
        bloco = f"--- {rel} ({pts} ocorrências) ---\n{'…' if ini else ''}{trecho}…"
        partes.append(bloco)
        gasto += len(bloco)
        if gasto > teto:
            break
    return "\n\n".join(partes)[:teto]


def de_card(card_ref, teto=TETO_POR_FONTE):
    try:
        sys.path.insert(0, os.path.expanduser("~/trinity/trello"))
        from trello_api import Trello
        from comum import Indice
        from cartao import id_do_nome
        t = Trello()
        idx = Indice(t)
        ref = str(card_ref).lstrip("#").strip()
        alvo = None
        for c in idx.cards():
            if c["id"] == ref or (id_do_nome(c.get("name")) or "").upper() == ref.upper():
                alvo = c
                break
        if not alvo:
            return f"(não achei o cartão {card_ref} no quadro)"
        lista = idx.listas_por_id.get(alvo.get("idList"), "?")
        corpo = (alvo.get("desc") or "").split("```quadro-dados")[0].strip()
        ck = []
        for chk in (t.checklists(alvo["id"]) or []):
            for item in chk.get("checkItems", []):
                marca = "x" if item.get("state") == "complete" else " "
                ck.append(f"  [{marca}] {item.get('name')}")
        return (f"CARTÃO: {alvo.get('name')}\nLISTA: {lista}\n\n{corpo}"
                + ("\n\nO QUE FALTA:\n" + "\n".join(ck) if ck else ""))[:teto]
    except Exception as e:
        return f"(o quadro não respondeu: {e})"


def montar(fontes, pedido="", teto=TETO_PADRAO):
    """O pacote inteiro, com origem declarada e teto respeitado."""
    if not fontes:
        return ""
    partes = []
    for f in fontes:
        tipo = (f or {}).get("tipo")
        if tipo == "pasta":
            corpo = de_pasta(f.get("caminho", ""))
            titulo = f"PASTA {f.get('caminho')}"
        elif tipo == "cofre":
            corpo = de_cofre(f.get("caminho", ""), f.get("busca") or pedido)
            titulo = f"COFRE {f.get('caminho')} · busca: {f.get('busca') or '(o próprio pedido)'}"
        elif tipo == "card":
            corpo = de_card(f.get("id", ""))
            titulo = f"CARTÃO {f.get('id')}"
        elif tipo == "arquivo":
            corpo = _ler(os.path.expanduser(f.get("caminho", "")), TETO_POR_FONTE)
            titulo = f"ARQUIVO {f.get('caminho')}"
        else:
            corpo, titulo = f"(fonte desconhecida: {tipo})", str(f)
        partes.append(f"═══ {titulo} ═══\n{corpo}")
    pacote = "\n\n".join(partes)
    if len(pacote) > teto:
        pacote = pacote[:teto] + "\n… (pacote cortado no teto)"
    return pacote


if __name__ == "__main__":
    print("── prova: pasta ──")
    print(de_pasta("~/esteira")[:400])
    print("\n── prova: cofre real (cerebro-obsidian, busca 'mercado livre anúncio') ──")
    r = de_cofre("~/Downloads/cerebro-obsidian", "mercado livre anúncio")
    print(r[:600])
    print("\n── prova: card #A1 ──")
    print(de_card("A1")[:400])
