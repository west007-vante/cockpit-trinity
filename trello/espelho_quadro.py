#!/usr/bin/env python3
"""O espelho — o Trello passa a mandar, o tasks.json vira reflexo dele.

Decisão do Pyerri: "Trello manda". Mas mandar não é atropelar. Este arquivo é
uma CAMADA POR CIMA do build_index.py, não um substituto:

    build_index.py   →  tasks.json  (tarefas curadas + índice de sessões)
                              ↓
    espelho_quadro   →  aplica o estado do Trello por cima
                              ↓
                        tasks.json final

Assim o `resolver.py`, a skill `task` e o canvas continuam funcionando sem
nenhuma alteração — eles leem o mesmo arquivo de sempre, só que agora o estado
(faixa e status) vem de onde você e o Davi realmente mexem: o quadro.

O que o espelho faz:
  · card movido no Trello  →  muda faixa/status da tarefa
  · card novo com #ID      →  entra no tasks.json
  · card sem #ID           →  entra como tarefa nova, com ID gerado na área certa
  · tarefa que sumiu do quadro → NÃO apaga. Marca `fora_do_quadro` e conta.
    Apagar tarefa por ausência é como o índice perde trabalho de verdade.

    python3 espelho_quadro.py --conferir    # mostra o que mudaria
    python3 espelho_quadro.py               # grava
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cartao import id_do_nome, ler_desc                                # noqa: E402
from comum import (AREAS, Indice, L_ADIADO, L_BANCADA, L_CLIENTES,     # noqa: E402
                   L_DESCARTADO, L_ENTRADA, L_FAZENDO, L_FEITO,
                   L_HOJE, L_PARADO, L_TAREFAS)

TASKS = os.path.expanduser("~/quadro/tasks.json")
BUILD = os.path.expanduser("~/quadro/build_index.py")

# lista do Trello → (faixa, status) no vocabulário do Quadro da Obra
DE_VOLTA = {
    L_HOJE:       ("agora",   None),
    L_FAZENDO:    ("agora",   "fazendo"),
    L_TAREFAS:    ("semana",  None),
    L_ENTRADA:    ("semana",  "triar"),
    L_PARADO:     (None,      "terceiro"),
    L_ADIADO:     ("fila",    "fila"),
    L_FEITO:      (None,      "pronto"),
    L_DESCARTADO: (None,      "descartado"),
    L_BANCADA:    ("fila",    "bancada"),
    L_CLIENTES:   (None,      "cliente"),
}


def rodar_build():
    """Roda o build_index primeiro — ele é quem indexa as sessões."""
    if not os.path.exists(BUILD):
        return False
    try:
        r = subprocess.run([sys.executable, BUILD], capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


def proximo_id(tasks, area):
    ns = [int(k[1:]) for k in tasks if k[0] == area and k[1:].isdigit()]
    return f"{area}{max(ns) + 1 if ns else 1}"


def main():
    conferir = "--conferir" in sys.argv

    from trello_api import Trello, TrelloErro
    try:
        t = Trello()
        if not t.board_id:
            print("❌ TRELLO_BOARD_ID vazio.")
            return 1
        idx = Indice(t)
    except TrelloErro as e:
        print(f"❌ {e}")
        return 1

    if not conferir:
        rodar_build()          # o build reindexa as sessões antes de espelharmos

    if not os.path.exists(TASKS):
        print(f"❌ não achei {TASKS}")
        return 1
    d = json.load(open(TASKS, encoding="utf-8"))
    tasks = d.get("tasks") or {}
    antes = json.dumps(tasks, sort_keys=True, ensure_ascii=False)

    vistos, mudancas, novas = set(), [], []
    for c in idx.cards():
        lista = idx.listas_por_id.get(c.get("idList"), "")
        if lista not in DE_VOLTA:
            continue
        dados = ler_desc(c.get("desc")) or {}
        tid = id_do_nome(c.get("name")) or dados.get("id")
        faixa, status = DE_VOLTA[lista]

        if tid and tid in tasks:
            vistos.add(tid)
            alvo = tasks[tid]
            for campo, valor in (("faixa", faixa), ("status", status)):
                if valor and alvo.get(campo) != valor:
                    mudancas.append((tid, campo, alvo.get(campo), valor, c["name"][:40]))
                    if not conferir:
                        alvo[campo] = valor
            if not conferir:
                alvo["trello"] = c.get("shortUrl")
                if c.get("start"):
                    alvo["agendado"] = c["start"]
            continue

        # card que não existe no índice → tarefa nova, nascida no quadro
        if lista in (L_FEITO, L_DESCARTADO, L_CLIENTES):
            continue                     # fim de linha e cliente não viram tarefa
        area = dados.get("area") or "G"
        novo_id = tid or proximo_id(tasks, area)
        while novo_id in tasks:
            novo_id = proximo_id(tasks, area)
        novas.append((novo_id, c["name"][:70], lista))
        if not conferir:
            tasks[novo_id] = {
                "id": novo_id, "area": area, "area_nome": AREAS.get(area, "?"),
                "faixa": faixa or "semana", "status": status or "voce",
                "titulo": c["name"], "u": dados.get("u", 3), "i": dados.get("i", 3),
                "e": dados.get("e", 2),
                "peso": (dados.get("u", 3) + dados.get("i", 3)),
                "dep": [], "descricao": (c.get("desc") or "").split("```")[0].strip()[:1200],
                "fonte": f"nasceu no quadro do Trello · {c.get('shortUrl')}",
                "falta": [], "sessoes": [], "trello": c.get("shortUrl"),
                "origem": dados.get("origem", "trello"),
            }
            vistos.add(novo_id)

    sumiram = [k for k in tasks if k not in vistos and not tasks[k].get("fora_do_quadro")]

    # ------------------------------------------------------------------ relatar
    print(f"quadro: {len(idx.cards())} card(s) · índice: {len(tasks)} tarefa(s)\n")
    if mudancas:
        print(f"  ── estado mudado no Trello ({len(mudancas)}) ──")
        for tid, campo, de, para, nome in mudancas[:15]:
            print(f"     #{tid:4s} {campo:6s}: {str(de):12s} → {para:12s}  {nome}")
        if len(mudancas) > 15:
            print(f"     … e mais {len(mudancas) - 15}")
        print()
    if novas:
        print(f"  ── nasceram no quadro ({len(novas)}) ──")
        for tid, nome, lista in novas[:12]:
            print(f"     #{tid:4s} {lista:14s} {nome}")
        print()
    if sumiram:
        print(f"  ── no índice mas não no quadro ({len(sumiram)}) ──")
        print(f"     {' '.join('#' + s for s in sumiram[:20])}")
        print("     Não apago: só marco. Apagar por ausência perde trabalho de verdade.\n")

    if conferir:
        print("MODO CONFERÊNCIA — nada foi gravado.")
        return 0

    for k in sumiram:
        tasks[k]["fora_do_quadro"] = True

    if json.dumps(tasks, sort_keys=True, ensure_ascii=False) == antes:
        print("nada mudou.")
        return 0

    shutil.copy(TASKS, TASKS + ".antes-do-espelho")
    d["tasks"] = tasks
    d["total"] = len(tasks)
    d["espelhado_em"] = time.strftime("%d/%m/%Y %H:%M")
    d["espelho_fonte"] = t.board().get("shortUrl")
    with open(TASKS, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print(f"✅ {TASKS} atualizado ({len(mudancas)} mudança(s), {len(novas)} nova(s))")
    print(f"   backup: {TASKS}.antes-do-espelho")
    return 0


if __name__ == "__main__":
    sys.exit(main())
