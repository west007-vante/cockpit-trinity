#!/usr/bin/env python3
"""O roteador — pega a fila do worklog e transforma em card no quadro.

    fila.jsonl (o hook enche)  →  classificador  →  card no Trello

Regras que ele obedece:
  · Conversa fiada nunca chega aqui — morre no hook. A lei do Pyerri.
  · Não casou numa frente conhecida → 📥 Entrada com o motivo escrito no card.
    Nunca chuta.
  · Mesmo trabalho continuado (mesmo título, card ainda vivo) vira COMENTÁRIO no
    card que já existe, não card novo. Senão o quadro vira enxurrada.
  · O robô não mexe em card que está em Parado, Adiado ou Descartado — decisão
    humana mora lá.

    python3 roteador.py --conferir   # sem credencial: mostra o que faria
    python3 roteador.py              # roda pra valer
"""
import json
import os
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cartao import ler_desc, montar_desc                                # noqa: E402
from classificador import carregar_rotas, classificar                   # noqa: E402
from comum import INTOCAVEIS, Indice, VIVAS, lista_do_veredito          # noqa: E402

DIR = os.path.expanduser("~/.steve/worklog")
FILA = os.path.join(DIR, "fila.jsonl")
FEITA = os.path.join(DIR, "fila-feita.jsonl")


def _chave(t):
    """Título normalizado — pra reconhecer o mesmo trabalho voltando."""
    t = unicodedata.normalize("NFD", (t or "").lower())
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").split())


def tomar_fila(caminho=FILA):
    """Pega a fila inteira de uma vez e some com ela (rename é atômico).

    O hook continua escrevendo numa fila nova enquanto processamos a velha —
    nada se perde e nada é processado duas vezes.
    """
    if not os.path.exists(caminho):
        return [], None
    trabalhando = f"{caminho}.processando.{os.getpid()}"
    try:
        os.rename(caminho, trabalhando)
    except OSError:
        return [], None
    regs = []
    for ln in open(trabalhando, encoding="utf-8"):
        ln = ln.strip()
        if not ln:
            continue
        try:
            regs.append(json.loads(ln))
        except Exception:
            pass
    return regs, trabalhando


def espiar_fila(caminho=FILA):
    """Lê sem consumir — é o modo --conferir."""
    if not os.path.exists(caminho):
        return []
    out = []
    for ln in open(caminho, encoding="utf-8"):
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def _corpo(reg, v):
    """O texto humano do card: o que aconteceu, em português."""
    partes = []
    if reg.get("origem") == "pesquisa":
        mins = round(reg.get("duracao_s", 0) / 60)
        buscas = sum(reg.get("tools", {}).values())
        partes.append(f"Estudo de **{mins} min** — {buscas} busca(s)/leitura(s), "
                      f"sem mexer em arquivo. Caiu na Bancada por isso.")
    else:
        if reg.get("resumo"):
            partes.append(reg["resumo"].capitalize() + ".")
        arqs = reg.get("files") or []
        if arqs:
            mostra = "\n".join(f"- `{a}`" for a in arqs[:12])
            resto = f"\n- _…e mais {len(arqs) - 12}_" if len(arqs) > 12 else ""
            partes.append("**Arquivos tocados:**\n" + mostra + resto)
    quando = time.strftime("%d/%m %H:%M", time.localtime(reg.get("fim", time.time())))
    partes.append(f"_capturado do Claude Code de **{reg.get('owner','?')}** em {quando}_")
    return "\n\n".join(partes)


def processar(regs, t=None, idx=None, conferir=False, rotas=None):
    """Coração do roteador. Com conferir=True não toca em rede nenhuma."""
    rotas = rotas or carregar_rotas()
    vivos = {}
    if idx:
        for c in idx.cards():
            nome_lista = idx.listas_por_id.get(c.get("idList"), "")
            if nome_lista in VIVAS:
                vivos.setdefault(_chave(c.get("name")), c)

    acoes = []
    for reg in regs:
        v = classificar(reg.get("files"), reg.get("title"), reg.get("tools"), rotas=rotas)
        if reg.get("origem") == "pesquisa" and v["tipo"] == "entrada":
            # já sabemos que foi estudo — o hook mediu. Bancada é o lugar certo.
            v = {**v, "tipo": "bancada", "rotulo": "Bancada",
                 "motivo": "turno só de pesquisa, acima do tempo mínimo"}
        lista = lista_do_veredito(v["tipo"])
        k = _chave(reg.get("title"))
        existente = vivos.get(k)

        dados = {"origem": reg.get("origem", "trabalho"), "db_sid": reg.get("db_sid"),
                 "tipo": v["tipo"], "area": v["area"], "rotulo": v["rotulo"],
                 "dono": reg.get("owner"), "camada": v["camada"],
                 "confianca": v["confianca"], "motivo": v["motivo"],
                 "e": _esforco(reg)}

        acao = {"reg": reg, "v": v, "lista": lista, "dados": dados,
                "acao": "comentar" if existente else "criar",
                "card": existente}
        acoes.append(acao)

        if conferir or not t:
            continue

        try:
            if existente:
                t.comentar(existente["id"],
                           f"↻ voltou nisso agora — {reg.get('resumo') or 'mais trabalho'} "
                           f"({time.strftime('%d/%m %H:%M')})")
            else:
                labels = idx.etiquetas_de(v["tipo"], v["area"])
                membro = idx.membro(reg.get("owner"))
                c = t.criar_card(idx.lista(lista), (reg.get("title") or "trabalho")[:400],
                                 montar_desc(dados, _corpo(reg, v)),
                                 labels=labels,
                                 membros=[membro] if membro else None,
                                 pos="top")
                vivos[k] = c
                idx.cards().append(c)
            time.sleep(0.12)
        except Exception as e:
            acao["erro"] = str(e)
    return acoes


def _esforco(reg):
    """Chute honesto de esforço (1–5) pelo tamanho do trabalho — o agendador usa
    isso pra dimensionar o bloco. Card vindo do Quadro da Obra já traz o real."""
    n = len(reg.get("files") or [])
    dur = reg.get("duracao_s", 0)
    if n >= 8 or dur > 7200:
        return 4
    if n >= 3 or dur > 3600:
        return 3
    if n >= 1 or dur > 900:
        return 2
    return 1


def main():
    conferir = "--conferir" in sys.argv
    rotas = carregar_rotas()

    if conferir:
        regs = espiar_fila()
        print(f"fila: {len(regs)} item(ns) esperando\n")
        acoes = processar(regs, conferir=True, rotas=rotas)
        for a in acoes:
            v, reg = a["v"], a["reg"]
            print(f"  {a['acao'].upper():9s} → {a['lista']}")
            print(f"      {(reg.get('title') or '')[:70]}")
            print(f"      {v['tipo']}/{v['area'] or '-'} · {v['rotulo']} "
                  f"[{v['camada']}, confiança {v['confianca']}]")
            print(f"      motivo: {v['motivo']}\n")
        print("MODO CONFERÊNCIA — a fila não foi consumida, nada foi criado.")
        return

    from trello_api import Trello, TrelloErro
    try:
        t = Trello()
        if not t.board_id:
            print("❌ TRELLO_BOARD_ID vazio. Rode antes: python3 bootstrap_board.py")
            sys.exit(1)
        idx = Indice(t)
    except TrelloErro as e:
        print(f"❌ {e}")
        sys.exit(1)

    regs, arquivo = tomar_fila()
    if not regs:
        print("fila vazia — nada a fazer.")
        return
    print(f"processando {len(regs)} item(ns) da fila…")
    acoes = processar(regs, t, idx, rotas=rotas)

    criados = sum(1 for a in acoes if a["acao"] == "criar" and not a.get("erro"))
    coment = sum(1 for a in acoes if a["acao"] == "comentar" and not a.get("erro"))
    erros = [a for a in acoes if a.get("erro")]
    for a in acoes:
        marca = "⚠️" if a.get("erro") else ("➕" if a["acao"] == "criar" else "💬")
        print(f"  {marca} {a['lista']:14s} {(a['reg'].get('title') or '')[:56]}")
        if a.get("erro"):
            print(f"      {a['erro']}")

    # Só arquiva a fila depois de processar. Se deu erro, guarda de volta pra
    # não perder trabalho — o próximo ciclo tenta de novo.
    if erros:
        with open(FILA, "a", encoding="utf-8") as f:
            for a in erros:
                f.write(json.dumps(a["reg"], ensure_ascii=False) + "\n")
    if arquivo:
        with open(FEITA, "a", encoding="utf-8") as f:
            for a in acoes:
                if not a.get("erro"):
                    f.write(json.dumps(a["reg"], ensure_ascii=False) + "\n")
        os.remove(arquivo)
    print(f"\n✅ {criados} card(s) novo(s), {coment} comentário(s), {len(erros)} erro(s)")


if __name__ == "__main__":
    main()
