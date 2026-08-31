#!/usr/bin/env python3
"""OS GATILHOS — o que acorda um fluxo sem ninguém clicar.

  {"tipo":"manual"}                                  só no botão (o padrão)
  {"tipo":"horario","hora":"09:00","dias":["seg"]}   relógio (dias vazio = todo dia)
  {"tipo":"card-em-hoje"}                            um cartão ENTROU na lista Hoje
  {"tipo":"tarefa-concluida","card":"A1"}            o cartão X chegou em Feito
  {"tipo":"webhook","remetente":"davi"}              chegou webhook daquele remetente

A REGRA QUE NÃO DOBRA: gatilho automático dispara o fluxo NO MODO EM QUE ELE
ESTÁ. Fluxo em ensaio acorda em ensaio (você lê o diário e nada aconteceu);
só fluxo SOLTO executa de verdade. O relógio não tem mais autoridade que você.

Roda como laço dentro do servidor (thread), a cada 30 s. Estado (o que já foi
visto) em ~/.steve/esteira-gatilhos.json — reiniciar não redispara o passado.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda   # noqa: E402
import motor    # noqa: E402

CASA = os.path.dirname(os.path.abspath(__file__))
FLUXOS = os.path.join(CASA, "fluxos")
ESTADO = os.path.expanduser("~/.steve/esteira-gatilhos.json")
DIAS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]


def _estado():
    try:
        return json.load(open(ESTADO, encoding="utf-8"))
    except Exception:
        return {}


def _gravar_estado(e):
    try:
        os.makedirs(os.path.dirname(ESTADO), exist_ok=True)
        json.dump(e, open(ESTADO, "w", encoding="utf-8"))
    except Exception:
        pass


def _fluxos():
    out = []
    if not os.path.isdir(FLUXOS):
        return out
    for f in sorted(os.listdir(FLUXOS)):
        if f.endswith(".json"):
            try:
                d = json.load(open(os.path.join(FLUXOS, f), encoding="utf-8"))
                out.append((f, d))
            except Exception:
                pass
    return out


def _quadro():
    """Cartões por lista, uma chamada só por volta. Erro de rede = volta vazia
    (gatilho atrasa 30 s, não quebra)."""
    try:
        sys.path.insert(0, os.path.expanduser("~/trinity/trello"))
        from trello_api import Trello
        from comum import Indice
        t = Trello()
        idx = Indice(t)
        por = {}
        for c in idx.cards():
            por.setdefault(idx.listas_por_id.get(c.get("idList"), "?"), []).append(c)
        return por
    except Exception:
        return None


def _disparar(arquivo, fluxo, motivo, disparos):
    modo = "ensaio" if guarda.em_ensaio(fluxo) else "valendo"
    pode, modo2, recados = guarda.liberado_pra_rodar(fluxo, forcar_ensaio=(modo == "ensaio"))
    reg = {"quando": time.strftime("%d/%m %H:%M:%S"), "fluxo": fluxo.get("nome", arquivo),
           "motivo": motivo, "modo": modo2 if pode else "barrado"}
    disparos.append(reg)
    if not pode:
        return reg
    try:
        out = motor.rodar(fluxo, modo2)
        reg["diario"] = out["diario"]
        reg["executados"] = out["executados"]
    except Exception as e:
        reg["erro"] = str(e)
    return reg


def uma_volta(agora=None, quadro=None, eventos_novos=None, disparos=None):
    """Uma passada por todos os gatilhos. Separada do laço pra ser testável:
    dá pra injetar hora, quadro e eventos falsos e provar cada gatilho sem
    esperar relógio nenhum."""
    agora = agora or time.localtime()
    est = _estado()
    disparos = disparos if disparos is not None else []
    quadro_cache = quadro          # None = ainda não buscou; busca só se precisar

    for arquivo, fluxo in _fluxos():
        g = fluxo.get("gatilho") or {}
        tipo = g.get("tipo", "manual")
        chave = f"{arquivo}:{tipo}"

        if tipo == "horario":
            alvo = g.get("hora", "")
            dias = g.get("dias") or []
            dia_ok = not dias or DIAS[agora.tm_wday] in dias
            marca = f"{time.strftime('%Y-%m-%d', agora)} {alvo}"
            if dia_ok and time.strftime("%H:%M", agora) == alvo and est.get(chave) != marca:
                est[chave] = marca            # dispara UMA vez por dia/horário
                _disparar(arquivo, fluxo, f"deu {alvo}", disparos)

        elif tipo == "card-em-hoje":
            if quadro_cache is None:
                quadro_cache = _quadro() or {}
            ids = sorted(c["id"] for c in quadro_cache.get("🗓️ Hoje", []))
            vistos = est.get(chave) or []
            novos = [i for i in ids if i not in vistos]
            # primeira volta só aprende o que já estava lá — não redispara o passado
            if vistos and novos:
                _disparar(arquivo, fluxo, f"{len(novos)} cartão(s) entraram em Hoje", disparos)
            est[chave] = ids

        elif tipo == "tarefa-concluida":
            if quadro_cache is None:
                quadro_cache = _quadro() or {}
            alvo = str(g.get("card", "")).lstrip("#").upper()
            feitos = []
            for c in quadro_cache.get("✅ Feito", []):
                nome = c.get("name", "")
                feitos.append(nome.split("—")[0].strip().lstrip("#").strip().upper())
            agora_feito = any(alvo and f.startswith(alvo) for f in feitos)
            if chave not in est:
                # primeira volta só APRENDE o estado — cartão que já estava em
                # Feito quando o gatilho nasceu não dispara surpresa nenhuma
                est[chave] = agora_feito
            else:
                if agora_feito and not est[chave]:
                    _disparar(arquivo, fluxo, f"#{alvo} chegou em Feito", disparos)
                est[chave] = agora_feito

        elif tipo == "webhook":
            quer = g.get("remetente")
            for ev in (eventos_novos or []):
                if not quer or ev.get("remetente") == quer:
                    _disparar(arquivo, fluxo,
                              f"webhook de {ev.get('remetente', '?')}", disparos)

    _gravar_estado(est)
    return disparos


def processar_recados():
    """Recados de sócio chegando NESTA máquina. A regra que não dobra:
    sem confiança (confianca.py) o nó roda em ENSAIO e devolve o ensaio —
    o remetente vê o encanamento vivo, o dono daqui mantém o controle.
    Com confiança, roda valendo — e o guarda local confere MESMO ASSIM."""
    import banco
    import confianca
    import motor
    try:
        novos = banco.recados_puxar()
    except Exception:
        return []
    feitos = []
    for rec in novos:
        rid, de = rec.get("id"), rec.get("de", "?")
        carga = rec.get("payload") or {}
        if rec.get("tipo") != "no" or not isinstance(carga.get("no"), dict):
            # recado de conversa (tipo "mensagem" do MCP) não executa nada —
            # fica marcado como feito com um aceno, pro remetente saber que chegou
            try:
                banco.recado_responder(rid, "feito",
                    {"ok": True, "saida": "recado recebido (sem execução — não é um nó)"})
            except Exception:
                pass
            continue
        no = dict(carga["no"])
        fluxo_nome = carga.get("fluxo_nome") or "sem-nome"
        confia = confianca.confiavel(de, fluxo_nome)
        fluxo1 = {"nome": f"recado-{rid}·{de}·{fluxo_nome}", "nos": [no], "fios": []}
        if confia:
            guarda.liberar(fluxo1, f"confianca.json ({de} → {fluxo_nome})")
        pode, modo, recados_g = guarda.liberado_pra_rodar(
            fluxo1, forcar_ensaio=not confia)
        if not pode:
            resposta = {"ok": False, "saida": " · ".join(recados_g)[:2000]}
            status = "recusado"
        else:
            # a saída do passo anterior do fluxo REMOTO entra como contexto
            no.setdefault("usar_saida_anterior", False)
            out = motor.rodar(fluxo1, modo)
            r = (out.get("resultado") or {}).get(no.get("id") or "", {}) or                 next(iter((out.get("resultado") or {}).values()), {})
            aviso = "" if confia else (
                " ⚠️ rodei em ENSAIO: o dono desta máquina ainda não liberou "
                f"este fluxo remoto (python3 confianca.py liberar {de} {fluxo_nome})")
            resposta = {"ok": r.get("ok", False), "saida": (r.get("saida") or "")[:6000] + aviso,
                        "modo": modo}
            status = "feito" if r.get("ok") else "erro"
        try:
            banco.recado_responder(rid, status, resposta)
            feitos.append({"id": rid, "de": de, "status": status, "modo": resposta.get("modo")})
        except Exception:
            pass
    return feitos


def laco(intervalo_s=30, pare=None):
    """O laço de verdade — roda dentro do servidor. `pare` é um threading.Event."""
    import modelos
    while not (pare and pare.is_set()):
        try:
            eventos = puxar_eventos_webhook()
            uma_volta(eventos_novos=eventos)
            processar_recados()
            modelos.derrubar_se_ocioso(10)      # 12 GB parados não são aluguel grátis
        except Exception:
            pass
        (pare.wait(intervalo_s) if pare else time.sleep(intervalo_s))


def puxar_eventos_webhook():
    """Busca eventos novos no banco (gravados pela Edge Function). A credencial
    da máquina mora em ~/.steve/esteira.env (ESTEIRA_CREDENCIAL). Sem credencial
    ou sem rede: lista vazia, o resto dos gatilhos segue vivo."""
    import urllib.request
    env = os.path.expanduser("~/.steve/esteira.env")
    cfg = {}
    try:
        for ln in open(env, encoding="utf-8"):
            if "=" in ln and not ln.strip().startswith("#"):
                k, _, v = ln.partition("=")
                cfg[k.strip()] = v.strip()
    except Exception:
        return []
    url = cfg.get("ESTEIRA_SUPABASE_URL")
    anon = cfg.get("ESTEIRA_SUPABASE_ANON")
    cred = cfg.get("ESTEIRA_CREDENCIAL")
    if not (url and anon and cred):
        return []
    try:
        corpo = json.dumps({"p_credencial": cred}).encode()
        req = urllib.request.Request(
            f"{url}/rest/v1/rpc/esteira_puxar_eventos", data=corpo,
            headers={"apikey": anon, "Authorization": f"Bearer {anon}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode()) or []
    except Exception:
        return []


if __name__ == "__main__":
    print("── uma volta na mão (sem laço) ──")
    d = uma_volta()
    print(f"  {len(d)} disparo(s)")
    for x in d:
        print("  ", x)
