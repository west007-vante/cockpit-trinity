#!/usr/bin/env python3
"""Sobe o Quadro da Obra (~/quadro/tasks.json) pro Trello. Roda 1×.

Cada tarefa vira um card:
  nome       #A1 — G7 autorizar o piloto de 10 anúncios
  lista      pela faixa + status (agora→Hoje, pronto→Feito, terceiro→Parado…)
  etiquetas  a área (A…I) + o tipo (obra/cliente)
  descrição  o texto + urgência/impacto/esforço + dependências + o rodapé de máquina
  checklist  a lista "o que falta" da tarefa, item por item

Idempotente: reconhece o card pelo #ID e ATUALIZA em vez de duplicar.

    python3 migrar_quadro.py --conferir    # funciona SEM credencial: só mostra o plano
    python3 migrar_quadro.py               # sobe pra valer
    python3 migrar_quadro.py --so A1,A2    # sobe só essas
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cartao import montar_desc, nome_do_card                      # noqa: E402
from comum import (AREAS, Indice, L_CLIENTES, lista_da_tarefa)    # noqa: E402

TASKS = os.path.expanduser("~/quadro/tasks.json")


def carregar_tarefas(caminho=TASKS):
    with open(caminho, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("tasks") or {}, d


def dados_do_card(tid, t):
    """O rodapé de máquina de uma tarefa do Quadro da Obra."""
    return {
        "id": tid, "origem": "quadro", "tipo": "cliente" if t.get("area") == "E" else "obra",
        "area": t.get("area"), "faixa": t.get("faixa"), "status": t.get("status"),
        "u": t.get("u"), "i": t.get("i"), "e": t.get("e"), "peso": t.get("peso"),
        "dep": t.get("dep") or None, "fonte": t.get("fonte"),
    }


def plano(tarefas, so=None):
    """O que a migração faria — computado sem tocar em rede. É o modo --conferir."""
    linhas = []
    for tid in sorted(tarefas, key=lambda x: (x[0], int(x[1:]))):
        if so and tid not in so:
            continue
        t = tarefas[tid]
        d = dados_do_card(tid, t)
        linhas.append({
            "id": tid,
            "nome": nome_do_card(tid, t.get("titulo", "")),
            "lista": lista_da_tarefa(t.get("faixa"), t.get("status")),
            "area": t.get("area"),
            "tipo": d["tipo"],
            "falta": len(t.get("falta") or []),
            "dados": d,
            "corpo": t.get("descricao") or "",
        })
    return linhas


def main():
    conferir = "--conferir" in sys.argv
    so = None
    for i, a in enumerate(sys.argv):
        if a == "--so" and i + 1 < len(sys.argv):
            so = {x.strip().upper().lstrip("#") for x in sys.argv[i + 1].split(",")}

    tarefas, bruto = carregar_tarefas()
    p = plano(tarefas, so)
    print(f"Quadro da Obra gerado em {bruto.get('gerado_em')} · {len(tarefas)} tarefas")
    print(f"vão subir: {len(p)}\n")

    porlista = {}
    for x in p:
        porlista.setdefault(x["lista"], []).append(x)
    for lista in sorted(porlista, key=lambda l: -len(porlista[l])):
        itens = porlista[lista]
        print(f"  {lista}  ({len(itens)})")
        for x in itens[:4]:
            check = f" · {x['falta']} item(ns) de checklist" if x["falta"] else ""
            print(f"      {x['nome'][:74]}{check}")
        if len(itens) > 4:
            print(f"      … e mais {len(itens) - 4}")
    print()

    if conferir:
        print("MODO CONFERÊNCIA — nada foi criado. Rode sem --conferir pra subir.")
        return

    # ---------------------------------------------------------------- subir mesmo
    from trello_api import Trello, TrelloErro
    t = Trello()
    if not t.board_id:
        print("❌ TRELLO_BOARD_ID vazio. Rode antes: python3 bootstrap_board.py")
        sys.exit(1)
    idx = Indice(t)
    ja = idx.por_task_id()
    print(f"quadro tem {len(idx.cards())} card(s), {len(ja)} com #ID\n")

    criados = atualizados = 0
    for x in p:
        tid = x["id"]
        desc = montar_desc(x["dados"], x["corpo"])
        labels = idx.etiquetas_de(x["tipo"], x["area"])
        try:
            if tid in ja:
                c = ja[tid]
                t.atualizar_card(c["id"], name=x["nome"], desc=desc,
                                 idLabels=",".join(labels) if labels else "")
                atualizados += 1
                print(f"  ✔ atualizado {tid}")
            else:
                c = t.criar_card(idx.lista(x["lista"]), x["nome"], desc, labels=labels)
                criados += 1
                print(f"  ➕ criado     {tid} → {x['lista']}")
                falta = (tarefas[tid].get("falta") or [])
                if falta:
                    ck = t.criar_checklist(c["id"], "O que falta")
                    for item in falta[:20]:
                        t.item_checklist(ck["id"], item)
            time.sleep(0.12)          # respeita o limite de 300 req/10s da chave
        except TrelloErro as e:
            print(f"  ⚠️  {tid}: {e}")

    # -------------------------------------------------------- os cards de cliente
    print()
    clientes = {}
    from classificador import carregar_rotas
    for nome in (carregar_rotas().get("palavras_chave", {}).get("cliente") or {}):
        clientes[nome] = True
    for r in carregar_rotas()["rotas"]:
        if r["tipo"] == "cliente":
            clientes[r["rotulo"]] = True
    nomes_existentes = {c["name"] for c in idx.cards(recarregar=True)}
    for nome in clientes:
        alvo = f"👤 {nome}"
        if alvo in nomes_existentes:
            print(f"  ✔ cliente já existe: {nome}")
            continue
        try:
            t.criar_card(idx.lista(L_CLIENTES), alvo,
                         montar_desc({"origem": "cliente", "tipo": "cliente",
                                      "cliente": nome}, ""))
            print(f"  ➕ cliente criado: {nome}")
        except TrelloErro as e:
            print(f"  ⚠️  cliente {nome}: {e}")

    print(f"\n✅ {criados} criado(s), {atualizados} atualizado(s)")
    print(f"   quadro: {t.board().get('shortUrl')}")


if __name__ == "__main__":
    main()
