#!/usr/bin/env python3
"""A CONFIANÇA — o freio da execução remota (o 9º, na prática).

Recado de sócio NÃO executa de verdade nesta máquina até VOCÊ liberar aquele
remetente+fluxo. Antes disso, roda em ENSAIO e devolve o ensaio — o remetente
vê que o encanamento funciona; a sua máquina continua sua.

A liberação é por (remetente, fluxo), gravada com data — nunca "libera tudo".

    python3 confianca.py                          # o que está liberado
    python3 confianca.py liberar rico meu-fluxo
    python3 confianca.py prender rico meu-fluxo
"""
import json
import os
import sys
import time

ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "confianca.json")


def _ler():
    try:
        return json.load(open(ARQ, encoding="utf-8"))
    except Exception:
        return {}


def confiavel(remetente, fluxo_nome):
    return bool(_ler().get(str(remetente), {}).get(str(fluxo_nome)))


def liberar(remetente, fluxo_nome, por="dono"):
    d = _ler()
    d.setdefault(remetente, {})[fluxo_nome] = {
        "por": por, "quando": time.strftime("%d/%m/%Y %H:%M:%S")}
    json.dump(d, open(ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return d[remetente][fluxo_nome]


def prender(remetente, fluxo_nome):
    d = _ler()
    if d.get(remetente, {}).pop(fluxo_nome, None) is not None:
        json.dump(d, open(ARQ, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return True
    return False


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] == "liberar":
        print("✅ liberado:", liberar(a[1], a[2]))
    elif len(a) == 3 and a[0] == "prender":
        print("✅ preso de volta" if prender(a[1], a[2]) else "não estava liberado")
    else:
        d = _ler()
        if not d:
            print("nada liberado — todo recado remoto roda em ensaio.")
        for rem, fluxos in d.items():
            for fl, info in fluxos.items():
                print(f"  {rem} → {fl}  (desde {info['quando']})")
