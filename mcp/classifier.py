#!/usr/bin/env python3
"""Classificador + Analista de operação do cockpit Trinity.

PROBLEMA que resolve: o worklog mostra um monte de log cru — ninguém sabe se o que
cada sócio faz no Claude Code está alinhado com criar/avançar as NOSSAS ofertas.

O QUE FAZ (roda na máquina do Pyerri, que tem o claude CLI + service key):
  1) CLASSIFICA cada work_session concluída ainda não-classificada: pergunta ao
     Claude (CLI local, SEM ANTHROPIC_API_KEY) se o trabalho tem a ver com CRIAR ou
     AVANÇAR uma oferta nossa (cockpit_offers em esteira/produção).
       - Não-relacionado (conversa, trabalho alternativo) -> relevante=false ("passa",
         só fica de log, NÃO conta). Na dúvida, passa. (Lei Zero: conservador.)
       - Relacionado -> qual oferta, categoria, estágio, progresso (rubrica abaixo).
  2) ANALISA + AGREGA: progresso de cada oferta (cockpit_offers.progresso) e os KPIs
     (cockpit_results) — Criativos/dia, Posts/dia, Ofertas no roadmap, Progresso das
     ofertas (headline), Receita (REAL, de commerce_sales — nunca inventada).
  -> Tudo isso tem realtime ligado no cockpit: muda aqui, acende lá na hora.

Roda em loop via launchd (StartInterval). Idempotente, defensivo, nunca trava.
"""
import datetime
import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

BATCH = int(os.environ.get("BATCH", "12"))

# estágio -> progresso (%). Rubrica única, rastreável.
ESTAGIOS = {"pesquisa": 10, "oferta": 30, "copy": 40, "criativo": 55,
            "landing": 70, "checkout": 80, "publicado": 90, "vendendo": 100}


def _load_env():
    for p in [os.path.expanduser("~/Dev/steve-backend/.env"), os.path.expanduser("~/.steve/worklog.env")]:
        if os.path.exists(p):
            cfg = {}
            for ln in open(p, encoding="utf-8"):
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, _, v = ln.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
            url = cfg.get("NEXT_PUBLIC_SUPABASE_URL") or cfg.get("SUPABASE_URL")
            key = cfg.get("SUPABASE_SERVICE_KEY") or cfg.get("SUPABASE_SERVICE_ROLE_KEY") or cfg.get("SUPABASE_KEY")
            if url and key:
                return url, key
    return os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")


URL, KEY = _load_env()
CLAUDE = os.environ.get("CLAUDE_BIN") or os.path.expanduser("~/.local/bin/claude")
if not os.path.exists(CLAUDE):
    CLAUDE = "claude"


def _req(method, path, body=None, params=""):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        f"{URL}/rest/v1/{path}{params}", data=data, method=method,
        headers={"apikey": KEY, "Authorization": "Bearer " + KEY,
                 "Content-Type": "application/json", "Prefer": "return=representation"})
    with urllib.request.urlopen(r, timeout=15) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else []


def _claude(prompt):
    """Claude CLI local — login Max, ZERO ANTHROPIC_API_KEY (removida do env)."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    p = subprocess.run([CLAUDE, "--print", "--output-format", "text", "--max-turns", "1", "-p", prompt],
                       capture_output=True, text=True, env=env, timeout=120)
    return (p.stdout or "").strip()


def _extract_json(s):
    s = re.sub(r"```[a-z]*", "", s).replace("```", "").strip()
    m = re.search(r"\{.*\}", s, re.S)
    return json.loads(m.group(0)) if m else None


def classify_one(ws, offers):
    offer_lines = "\n".join(
        f"  - id {o['id']}: {o['title']} ({o.get('niche', '')}) [{o['status']}]" for o in offers)
    prompt = f"""Você é o CLASSIFICADOR de operação do Steve. Lei Zero: honesto, conservador, rastreável.
Decida se este TRABALHO feito no Claude Code tem a ver com CRIAR ou AVANÇAR uma das NOSSAS ofertas
abaixo (que estão na esteira ou em produção). Se for conversa, estudo solto, ou trabalho alternativo
que NÃO é sobre criar nossas ofertas, marque relevante=false (ele só "passa", não conta). NA DÚVIDA, relevante=false.

NOSSAS OFERTAS (esteira/produção):
{offer_lines or '  (nenhuma cadastrada)'}

TRABALHO:
  dono: {ws.get('owner')}
  título (o que a pessoa pediu): {(ws.get('title') or '')[:500]}
  resumo: {(ws.get('summary') or '')[:300]}
  arquivos mexidos: {json.dumps(ws.get('files') or [])[:300]}
  pasta: {ws.get('cwd') or ''}

categoria = tipo de trabalho. estagio = em que ponto a oferta fica com este trabalho:
pesquisa<oferta<copy<criativo<landing<checkout<publicado<vendendo.

Responda SÓ com um JSON numa linha, sem texto antes/depois:
{{"relevante":true|false,"offer_id":<id da oferta ou null>,"categoria":"pesquisa|oferta|copy|criativo|landing|checkout|publicacao|setup|outro","estagio":"pesquisa|oferta|copy|criativo|landing|checkout|publicado|vendendo|null","confidence":0-100,"motivo":"1 frase curta e rastreável"}}"""
    try:
        j = _extract_json(_claude(prompt))
    except Exception:
        j = None
    if not j:
        return None
    relevante = bool(j.get("relevante"))
    try:
        offer_id = int(j["offer_id"]) if relevante and j.get("offer_id") not in (None, "", "null") else None
    except (ValueError, TypeError):
        offer_id = None
    estagio = j.get("estagio") if relevante else None
    if estagio in ("null", ""):
        estagio = None
    progresso = ESTAGIOS.get(estagio or "", 0) if relevante else 0
    label = next((o["title"] for o in offers if o["id"] == offer_id), None)
    return {"relevante": relevante, "categoria": j.get("categoria"), "offer_id": offer_id,
            "offer_label": label, "estagio": estagio, "progresso": progresso,
            "confidence": j.get("confidence"), "motivo": (j.get("motivo") or "")[:300]}


def analyst(offers):
    """Agrega o que foi classificado nos KPIs + progresso das ofertas."""
    rel = _req("GET", "work_sessions",
               params="?select=offer_id,categoria,estagio,progresso,updated_at&relevante=is.true")
    by_offer = {}
    for w in rel:
        if w.get("offer_id") is not None:
            by_offer.setdefault(w["offer_id"], []).append(w)
    for o in offers:
        ws = sorted(by_offer.get(o["id"], []), key=lambda x: x.get("progresso") or 0, reverse=True)
        if ws:
            _req("PATCH", f"cockpit_offers?id=eq.{o['id']}",
                 {"progresso": ws[0].get("progresso") or 0, "estagio": ws[0].get("estagio")})

    today = datetime.date.today().isoformat()
    def count_cat(cats):
        return len([w for w in rel if w.get("categoria") in cats and str(w.get("updated_at") or "")[:10] == today])
    criativos = count_cat({"criativo"})
    posts = count_cat({"publicacao"})

    offers_now = _req("GET", "cockpit_offers", params="?select=id,progresso,status,result_brl")
    ofertas_andando = len([o for o in offers_now if (o.get("progresso") or 0) > 0])
    pipeline = [o for o in offers_now if o.get("status") in ("esteira", "producao")]
    avg_prog = round(sum(o.get("progresso") or 0 for o in pipeline) / len(pipeline)) if pipeline else 0

    # LEI ZERO: "Receita gerada" = receita das NOSSAS ofertas (cockpit_offers.result_brl).
    # NÃO usar commerce_sales — aquilo é faturamento de cliente TERCEIRO que o Steve só
    # rastreia. Contar isso como receita nossa foi exatamente o erro do deck que criou a
    # Lei Zero. Receita atribuível às ofertas do cockpit hoje = R$0 [VERIFICADO].
    receita = round(sum(float(o.get("result_brl") or 0) for o in offers_now))

    def upd(metric, generated, expected=None):
        body = {"generated": generated}
        if expected is not None:
            body["expected"] = expected
        _req("PATCH", f"cockpit_results?metric=eq.{urllib.parse.quote(metric)}", body)

    upd("Criativos / dia", criativos)
    upd("Posts / dia", posts)
    upd("Ofertas no roadmap", ofertas_andando, max(len(offers_now), 1))
    upd("Progresso das ofertas", avg_prog, 100)
    upd("Receita gerada", receita)
    print(f"KPIs: criativos/dia={criativos} posts/dia={posts} ofertas_andando={ofertas_andando}/{len(offers_now)} "
          f"progresso_medio_ofertas={avg_prog}% receita_real=R${receita}")


def main():
    if not (URL and KEY):
        print("sem SUPABASE_URL/SERVICE_KEY — abortando")
        return
    offers = _req("GET", "cockpit_offers",
                  params="?select=id,title,niche,status&status=in.(esteira,producao,feita)&order=id")
    ofilter = f"&owner=eq.{os.environ['OWNER']}" if os.environ.get("OWNER") else ""
    pend = _req("GET", "work_sessions",
                params=f"?select=*&status=eq.concluida&classified_at=is.null{ofilter}&order=updated_at.desc&limit={BATCH}")
    print(f"{len(pend)} sessões pendentes · {len(offers)} ofertas nossas")
    for ws in pend:
        cl = classify_one(ws, offers)
        if cl is None:
            print(f"  #{ws['id']} {ws.get('owner')}: classificação falhou (tenta na próxima)")
            continue
        cl["classified_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        cl["classifier"] = "claude-cli"
        try:
            _req("PATCH", f"work_sessions?id=eq.{ws['id']}", cl)
        except Exception as e:
            print(f"  #{ws['id']} PATCH falhou: {e}")
            continue
        tag = f"✅ {cl['categoria']} → {cl['offer_label']} ({cl['progresso']}%)" if cl["relevante"] else "⚪ passa (fora da esteira)"
        print(f"  #{ws['id']} {ws.get('owner')}: {tag} — {cl['motivo'][:70]}")
    analyst(offers)
    print("done")


if __name__ == "__main__":
    main()
