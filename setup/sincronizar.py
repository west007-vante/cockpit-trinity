#!/usr/bin/env python3
"""SINCRONIZAR — leva as sessões de trabalho pra Ponte, já faxinadas.

Só sobe sessão que o worklog já reconheceu como TRABALHO. Conversa pura
nunca entra aqui — ela nem tem work_session pra casar.

O caminho é sempre o mesmo: transcript → markdown → FAXINA → banco.
Nada sai da máquina sem passar pelo filtro.

Uso:
    python3 sincronizar.py              # sobe o que falta ou mudou
    python3 sincronizar.py --tudo       # re-sobe tudo (depois de mexer na faxina)
    python3 sincronizar.py --seco       # mostra o que faria, sem subir nada
"""
import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exportar_sessao import exportar  # noqa: E402

HOME = os.path.expanduser("~")
ENV = os.path.join(HOME, ".steve", "ponte.env")
TRANSCRIPTS = os.path.join(HOME, ".claude", "projects", "-Users-pyerri")
CACHE = os.path.join(HOME, ".steve", "sincronizado.json")
LIMITE_BYTES = 2 * 1024 * 1024      # 2 MB por sessão


def _env():
    cfg = {}
    try:
        for ln in open(ENV, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, _, v = ln.partition("=")
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        sys.exit(f"não achei {ENV} — rode o instalador da travessia primeiro")
    faltam = [k for k in ("SUPABASE_URL", "SUPABASE_KEY", "PONTE_TOKEN", "TRINITY_OWNER") if not cfg.get(k)]
    if faltam:
        sys.exit(f"faltam no {ENV}: {', '.join(faltam)}")
    return cfg


def _rpc(cfg, funcao, corpo):
    req = urllib.request.Request(
        f"{cfg['SUPABASE_URL']}/rest/v1/rpc/{funcao}",
        data=json.dumps(corpo).encode(), method="POST")
    for h, v in {"apikey": cfg["SUPABASE_KEY"],
                 "Authorization": f"Bearer {cfg['SUPABASE_KEY']}",
                 "Content-Type": "application/json"}.items():
        req.add_header(h, v)
    with urllib.request.urlopen(req, timeout=45) as r:
        bruto = r.read().decode()
        return json.loads(bruto) if bruto else None


def main():
    cfg = _env()
    tudo = "--tudo" in sys.argv
    seco = "--seco" in sys.argv

    # quais sessões o worklog já marcou como trabalho
    try:
        linhas = _rpc(cfg, "trinity_buscar",
                      {"p_token": cfg["PONTE_TOKEN"], "p_limite": 200,
                       "p_dono": cfg["TRINITY_OWNER"]}) or []
    except urllib.error.HTTPError as e:
        sys.exit(f"não consegui falar com a Ponte: {e.read().decode()[:200]}")

    cache = {}
    if os.path.exists(CACHE) and not tudo:
        try:
            cache = json.load(open(CACHE))
        except Exception:
            cache = {}

    subiu = pulou = falhou = 0
    for l in linhas:
        db_sid = l["session_id"]
        uuid = db_sid.split(":")[0]
        caminho = os.path.join(TRANSCRIPTS, f"{uuid}.jsonl")
        if not os.path.exists(caminho):
            continue

        marca = f"{os.path.getmtime(caminho):.0f}:{os.path.getsize(caminho)}"
        if cache.get(db_sid) == marca and not tudo:
            pulou += 1
            continue

        try:
            md, meta = exportar(caminho)
        except Exception as e:
            print(f"  ✗ {uuid[:8]} não exportou: {e}")
            falhou += 1
            continue

        if len(md.encode()) > LIMITE_BYTES:
            md = md[:LIMITE_BYTES] + "\n\n> ✂️ *sessão longa — cortada no limite de 2 MB.*"

        titulo = l.get("titulo") or "sessão"
        print(f"  {'·' if seco else '↑'} {uuid[:8]}  {len(md)//1024:>4} KB  "
              f"🧽{meta['mascarados']:<3} {titulo[:52]}")
        if seco:
            continue

        try:
            _rpc(cfg, "trinity_gravar_sessao", {
                "p_token": cfg["PONTE_TOKEN"], "p_session_id": db_sid,
                "p_owner": cfg["TRINITY_OWNER"], "p_titulo": titulo, "p_markdown": md,
                "p_mascarados": meta["mascarados"], "p_pedidos": meta["pedidos"],
                "p_respostas": meta["respostas"], "p_ferramentas": meta["ferramentas"],
                "p_comecou": meta["inicio"], "p_terminou": meta["fim"]})
            cache[db_sid] = marca
            subiu += 1
        except urllib.error.HTTPError as e:
            print(f"    ✗ {e.code}: {e.read().decode()[:160]}")
            falhou += 1

    if not seco:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w"))
    print(f"\n{'(simulação) ' if seco else ''}{subiu} subiram · {pulou} já estavam · {falhou} falharam")


if __name__ == "__main__":
    main()
