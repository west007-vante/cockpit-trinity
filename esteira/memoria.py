#!/usr/bin/env python3
"""A MEMÓRIA — o que o agente lembra entre uma rodada e outra.

Três tipos, escolhidos por nó (o pedido do dono, ao pé da letra):

  comum      todos os agentes dos três sócios leem e escrevem.
             Vive em ~/esteira/memoria/comum.md (na F3 sincroniza com o banco
             esteira.memoria_comum — o arquivo já nasce no formato certo).
  tarefa     só daquela rodada. Nasce na pasta da execução, morre com ela.
  isolada    permanente, mas só daquele agente: ~/esteira/memoria/<nome>/.

O formato é markdown datado — legível pra pessoa, tratável pra máquina.
O motor carrega ANTES (entra no prompt) e grava DEPOIS (o que aconteceu).
"""
import os
import time

CASA = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.join(CASA, "memoria")
TETO_LEITURA = 9000        # a memória entra no prompt — teto pra não virar fatura


def _caminho(mem, pasta_execucao=None):
    tipo = (mem or {}).get("tipo") or "tarefa"
    if tipo == "comum":
        return os.path.join(RAIZ, "comum.md")
    if tipo == "isolada":
        nome = "".join(c for c in (mem.get("nome") or "sem-nome")
                       if c.isalnum() or c in "-_")[:40] or "sem-nome"
        return os.path.join(RAIZ, nome, "memoria.md")
    # tarefa: mora junto do diário daquela execução
    return os.path.join(pasta_execucao or os.path.join(CASA, "execucoes"),
                        "memoria-da-tarefa.md")


def carregar(mem, pasta_execucao=None):
    """O que o agente lembra. Vazio se nunca lembrou de nada — sem erro."""
    p = _caminho(mem, pasta_execucao)
    try:
        with open(p, encoding="utf-8") as f:
            corpo = f.read()
    except FileNotFoundError:
        return ""
    # se passou do teto, entrega o FIM (o mais recente é o que importa)
    return corpo[-TETO_LEITURA:] if len(corpo) > TETO_LEITURA else corpo


def gravar(mem, titulo, registro, pasta_execucao=None):
    """Apende um bloco datado. Nunca reescreve o passado."""
    p = _caminho(mem, pasta_execucao)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    bloco = (f"\n## {time.strftime('%d/%m/%Y %H:%M')} · {titulo}\n"
             f"{(registro or '').strip()[:2500]}\n")
    with open(p, "a", encoding="utf-8") as f:
        f.write(bloco)
    return p


def apagar_da_tarefa(pasta_execucao):
    """A memória 'tarefa' morre com a rodada — é a promessa do tipo."""
    p = os.path.join(pasta_execucao, "memoria-da-tarefa.md")
    try:
        os.remove(p)
        return True
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    import tempfile, shutil
    ok = 0
    print("── os três tipos, ida e volta ──")

    m = {"tipo": "isolada", "nome": "prova-automática"}
    gravar(m, "primeira rodada", "o agente aprendeu X")
    gravar(m, "segunda rodada", "o agente aprendeu Y")
    corpo = carregar(m)
    ok += "aprendeu X" in corpo and "aprendeu Y" in corpo
    print(f"  {'✅' if 'aprendeu Y' in corpo else '❌'} isolada: grava, acumula, volta")

    g = gravar({"tipo": "comum"}, "prova", "fato comum de teste")
    ok += "fato comum" in carregar({"tipo": "comum"})
    print(f"  ✅ comum: {g}")

    tmp = tempfile.mkdtemp()
    mt = {"tipo": "tarefa"}
    gravar(mt, "durante", "só desta rodada", pasta_execucao=tmp)
    tinha = "só desta rodada" in carregar(mt, pasta_execucao=tmp)
    apagar_da_tarefa(tmp)
    sumiu = carregar(mt, pasta_execucao=tmp) == ""
    ok += tinha and sumiu
    print(f"  {'✅' if tinha and sumiu else '❌'} tarefa: existe na rodada, morre no fim")

    # teto: memória gigante entrega só o fim (o recente)
    # o gravar corta cada bloco em 2500 — pra estourar o teto de LEITURA (9000)
    # precisa de vários blocos, não de um bloco gigante
    m2 = {"tipo": "isolada", "nome": "prova-teto"}
    gravar(m2, "velha", "COMEÇO-ANTIGO " + "x" * 2400)
    for i in range(4):
        gravar(m2, f"meio-{i}", "y" * 2400)
    gravar(m2, "nova", "FIM-RECENTE")
    c2 = carregar(m2)
    ok += ("FIM-RECENTE" in c2) and ("COMEÇO-ANTIGO" not in c2)
    print(f"  {'✅' if 'FIM-RECENTE' in c2 and 'COMEÇO-ANTIGO' not in c2 else '❌'} teto: memória grande entrega o recente, corta o antigo")

    # limpar as provas permanentes
    shutil.rmtree(os.path.join(RAIZ, "prova-automática"), ignore_errors=True)
    shutil.rmtree(os.path.join(RAIZ, "prova-teto"), ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{ok}/4 provas passaram")
    raise SystemExit(0 if ok == 4 else 1)
