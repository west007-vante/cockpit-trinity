#!/usr/bin/env python3
"""O agendador — decide QUE HORAS cada tarefa acontece.

Foi o pedido central: "já vai aparecer dentro da agenda o horário estipulado pra
cada um fazer essa tarefa, pra o dia ser padronizado".

Como ele decide:
  1. pega os cards vivos que ainda não têm horário
  2. ordena por urgência real: quem está em 🗓️ Hoje primeiro, depois por peso (u+i)
  3. converte o esforço (1–5) em minutos, pela tabela de rotas.json
  4. procura o primeiro buraco livre na janela de trabalho DO DONO do card,
     respeitando o que já está agendado — no quadro E na Google Agenda dele
  5. grava início/fim no card (aparece no Planner do Trello) e cria o evento
     na Google Agenda, com alarme

O que ele NÃO faz:
  · não mexe em card de Parado, Adiado ou Descartado — decisão humana mora lá
  · não remarca card que já tem horário (você mandou, está mandado)
  · não empurra mais trabalho pra um dia do que cabe na janela — e AVISA quando
    sobrou tarefa sem lugar, em vez de fingir que coube

    python3 agendador.py --conferir    # mostra a agenda que faria, sem gravar
    python3 agendador.py               # grava
    python3 agendador.py --sem-google  # só o Trello, sem tocar na agenda
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cartao import ler_desc, trocar_dados                             # noqa: E402
from classificador import carregar_rotas                              # noqa: E402
from comum import Indice, L_FAZENDO, L_HOJE, L_TAREFAS                # noqa: E402

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    TZ = None

DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
HORIZONTE = 14          # não agenda além de duas semanas: depois disso é ficção
AGENDAVEIS = (L_HOJE, L_TAREFAS, L_FAZENDO)


def _agora():
    return datetime.now(TZ) if TZ else datetime.now().astimezone()


def _hm(txt):
    h, m = txt.split(":")
    return int(h), int(m)


def janelas_do_dono(dono, rotas, dias=HORIZONTE, base=None):
    """Os pedaços de tempo em que esta pessoa pode trabalhar, dia a dia."""
    cfg = (rotas.get("janela_de_trabalho") or {}).get((dono or "").lower())
    if not cfg:
        cfg = {"todos": ["09:00", "18:00"]}
    base = base or _agora()
    out = []
    for d in range(dias):
        dia = (base + timedelta(days=d)).replace(second=0, microsecond=0)
        faixa = cfg.get("todos") or cfg.get(DIAS[dia.weekday()])
        if not faixa:
            continue                       # folga
        h0, m0 = _hm(faixa[0])
        h1, m1 = _hm(faixa[1])
        ini = dia.replace(hour=h0, minute=m0)
        fim = dia.replace(hour=h1, minute=m1)
        if fim <= base:
            continue                       # dia já passou
        out.append((max(ini, base), fim))
    return out


def encaixar(minutos, ocupado, janelas):
    """Acha o primeiro buraco de `minutos` que não pisa em nada já ocupado."""
    dur = timedelta(minutes=minutos)
    for ini_j, fim_j in janelas:
        cursor = ini_j
        # blocos ocupados que tocam esta janela, em ordem
        conflitos = sorted([(a, b) for a, b in ocupado if b > ini_j and a < fim_j])
        for a, b in conflitos:
            if cursor + dur <= a:
                return cursor, cursor + dur
            cursor = max(cursor, b)
        if cursor + dur <= fim_j:
            return cursor, cursor + dur
    return None, None


def _dono_do_card(c, idx, dados):
    """Quem faz. O membro atribuído manda; o rodapé é o plano B."""
    for mid in (c.get("idMembers") or []):
        for nome, i in idx.membros.items():
            if i == mid and not nome.startswith("@"):
                return nome
    return (dados.get("dono") or "pyerri").lower()


def _prioridade(c, idx, dados):
    """Menor = mais cedo. Hoje na frente; depois o peso; depois o mais velho."""
    lista = idx.listas_por_id.get(c.get("idList"), "")
    ordem_lista = {L_FAZENDO: 0, L_HOJE: 1, L_TAREFAS: 2}.get(lista, 3)
    peso = dados.get("peso") or ((dados.get("u") or 3) + (dados.get("i") or 3))
    return (ordem_lista, -peso, c.get("dateLastActivity") or "")


def main():
    conferir = "--conferir" in sys.argv
    sem_google = "--sem-google" in sys.argv
    rotas = carregar_rotas()
    dur_tab = rotas.get("duracao_por_esforco") or {}

    from trello_api import Trello, TrelloErro
    try:
        t = Trello()
        if not t.board_id:
            print("❌ TRELLO_BOARD_ID vazio. Rode: python3 bootstrap_board.py")
            return 1
        idx = Indice(t)
    except TrelloErro as e:
        print(f"❌ {e}")
        return 1

    # ------------------------------------------------- quem precisa de horário
    pendentes, ja_marcados = [], {}
    for c in idx.cards():
        lista = idx.listas_por_id.get(c.get("idList"), "")
        if lista not in AGENDAVEIS:
            continue
        d = ler_desc(c.get("desc")) or {}
        dono = _dono_do_card(c, idx, d)
        if c.get("start") and c.get("due"):
            try:
                a = datetime.fromisoformat(c["start"].replace("Z", "+00:00")).astimezone(TZ)
                b = datetime.fromisoformat(c["due"].replace("Z", "+00:00")).astimezone(TZ)
                ja_marcados.setdefault(dono, []).append((a, b))
            except Exception:
                pass
            continue
        pendentes.append((c, d, dono, lista))

    pendentes.sort(key=lambda x: _prioridade(x[0], idx, x[1]))
    print(f"{len(pendentes)} card(s) sem horário · "
          f"{sum(len(v) for v in ja_marcados.values())} já agendado(s)\n")
    if not pendentes:
        print("nada a agendar.")
        return 0

    # ----------------------------------- o que a Google Agenda já tem ocupado
    g = None
    if not sem_google:
        try:
            from gcal import GCal, GCalErro
            g = GCal()
            ini = _agora()
            fim = ini + timedelta(days=HORIZONTE)
            for ev in g.eventos(ini.isoformat(), fim.isoformat()):
                s, e = ev.get("start", {}), ev.get("end", {})
                if not s.get("dateTime"):
                    continue               # evento de dia inteiro não bloqueia
                try:
                    a = datetime.fromisoformat(s["dateTime"].replace("Z", "+00:00")).astimezone(TZ)
                    b = datetime.fromisoformat(e["dateTime"].replace("Z", "+00:00")).astimezone(TZ)
                    ja_marcados.setdefault("pyerri", []).append((a, b))
                except Exception:
                    pass
            print(f"Google Agenda: li os compromissos dos próximos {HORIZONTE} dias.\n")
        except Exception as e:
            print(f"⚠️  sem Google Agenda ({e}) — sigo só com o Trello.\n")
            g = None

    # --------------------------------------------------------------- encaixar
    janelas = {}
    marcados, sobraram = [], []
    for c, d, dono, lista in pendentes:
        if dono not in janelas:
            janelas[dono] = janelas_do_dono(dono, rotas)
        esf = d.get("e") or 2
        minutos = dur_tab.get(str(esf), dur_tab.get("padrao", 60))
        ini, fim = encaixar(minutos, ja_marcados.get(dono, []), janelas[dono])
        if not ini:
            sobraram.append((c, dono, minutos))
            continue
        ja_marcados.setdefault(dono, []).append((ini, fim))
        marcados.append((c, d, dono, ini, fim, minutos, lista))

    # ------------------------------------------------------------- mostrar/gravar
    por_dia = {}
    for m in marcados:
        por_dia.setdefault(m[3].strftime("%a %d/%m"), []).append(m)
    for dia in sorted(por_dia, key=lambda k: por_dia[k][0][3]):
        itens = por_dia[dia]
        horas = sum(m[5] for m in itens) / 60
        print(f"  ── {dia}  ({len(itens)} tarefa(s), {horas:.1f}h) ──")
        for c, d, dono, ini, fim, minutos, lista in itens:
            print(f"     {ini:%H:%M}–{fim:%H:%M}  [{dono:6s}] {c['name'][:52]}")
        print()

    if sobraram:
        print(f"  ⚠️  {len(sobraram)} tarefa(s) NÃO couberam em {HORIZONTE} dias de janela:")
        for c, dono, minutos in sobraram[:8]:
            print(f"       [{dono}] {c['name'][:60]} ({minutos} min)")
        if len(sobraram) > 8:
            print(f"       … e mais {len(sobraram) - 8}")
        print("     Isso não é bug: é a agenda te dizendo que tem mais tarefa que dia.\n")

    if conferir:
        print("MODO CONFERÊNCIA — nada foi gravado.")
        return 0

    gravados = 0
    for c, d, dono, ini, fim, minutos, lista in marcados:
        try:
            t.atualizar_card(c["id"], start=ini.isoformat(), due=fim.isoformat())
            novos = {**d, "agendado": ini.isoformat(), "minutos": minutos}
            if g:
                try:
                    ev = g.criar_evento(
                        c["name"][:200], ini.isoformat(), fim.isoformat(),
                        f"Bloco do QUADRO · {dono} · {minutos} min",
                        url_card=c.get("shortUrl"))
                    novos["gcal_id"] = ev.get("id")
                except Exception as e:
                    print(f"  ⚠️  agenda do Google recusou {c['name'][:40]}: {e}")
            t.atualizar_card(c["id"], desc=trocar_dados(c.get("desc", ""), novos))
            gravados += 1
        except Exception as e:
            print(f"  ⚠️  {c['name'][:40]}: {e}")

    print(f"✅ {gravados} card(s) com horário"
          + (" · eventos criados na Google Agenda" if g else " · (sem Google Agenda)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
