#!/usr/bin/env python3
"""Worklog hook — converte trabalho REAL do Claude Code em task no cockpit Trinity.

Nativo via hooks do Claude Code (settings.json):
  - PostToolUse (Write|Edit|MultiEdit|Bash|NotebookEdit): no 1º trabalho do turno,
    cria uma work_session "fazendo" no cockpit (aparece AO VIVO na home).
  - Stop (fim do turno): finaliza pra "concluida" com resumo + joga no feed.

Filtro do Pyerri: SÓ conta quando a sessão MEXEU em algo (criou/executou). Pergunta
e resposta pura (sem tool de trabalho) não toca em nada — turno sem trabalho = sem task.

Robustez sagrada: NUNCA trava nem quebra a sessão do sócio. Stdlib pura, timeout curto,
captura tudo, SEMPRE exit 0. Lê credenciais+dono de ~/.steve/worklog.env.

Estado por turno em ~/.steve/worklog/<session_id>.json (cria no 1º trabalho, apaga no Stop).
"""
import json
import os
import socket
import sys
import time
import urllib.request

WORK_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
STATE_DIR = os.path.expanduser("~/.steve/worklog")
ENV_FILE = os.path.expanduser("~/.steve/worklog.env")
PATCH_THROTTLE_S = 8  # não martela o banco em turno com muitos comandos


def _load_env():
    """Lê SUPABASE_URL, SUPABASE_KEY, TRINITY_OWNER do worklog.env (ou do ambiente)."""
    cfg = {}
    try:
        if os.path.exists(ENV_FILE):
            for ln in open(ENV_FILE, encoding="utf-8"):
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, _, v = ln.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    url = cfg.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = (cfg.get("SUPABASE_KEY") or cfg.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY"))
    owner = cfg.get("TRINITY_OWNER") or os.environ.get("TRINITY_OWNER")
    return url, key, owner


def _req(method, url, key, body=None):
    data = json.dumps(body).encode() if body is not None else None
    # return=minimal: NÃO pede a linha de volta. Essencial com a chave anon —
    # a leitura é gated em authenticated, então um RETURNING (representation)
    # faria a escrita falhar no SELECT pós-insert. Por isso o hook não depende
    # do id do banco: ele referencia a linha pelo session_id único do turno.
    h = {"apikey": key, "Authorization": f"Bearer {key}",
         "Content-Type": "application/json", "Prefer": "return=minimal"}
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=4) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else []


def _rpc(url, key, params):
    """Chama a função worklog_report (SECURITY DEFINER). É o ÚNICO caminho de escrita:
    a chave anon só EXECUTA essa função — não toca nas tabelas direto."""
    return _req("POST", f"{url}/rest/v1/rpc/worklog_report", key, params)


def _last_user_prompt(transcript_path):
    """Última mensagem HUMANA do transcript = o que ele pediu (vira o título)."""
    try:
        title = ""
        for ln in open(transcript_path, encoding="utf-8"):
            try:
                ev = json.loads(ln)
            except Exception:
                continue
            if ev.get("type") != "user":
                continue
            content = (ev.get("message") or {}).get("content")
            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                # ignora tool_result (não é prompt humano); pega blocos de texto
                if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    continue
                text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            text = (text or "").strip()
            if text and not text.startswith("<"):  # ignora prompts de sistema/comando
                title = text
        return title[:160]
    except Exception:
        return ""


def _state_path(sid):
    return os.path.join(STATE_DIR, f"{sid or 'nosess'}.json")


def _summary(files, tools):
    parts = []
    nf = len(files)
    if nf:
        amostra = ", ".join(os.path.basename(f) for f in files[:4])
        parts.append(f"{nf} arquivo(s) ({amostra}{'…' if nf > 4 else ''})")
    cmds = tools.get("Bash", 0)
    if cmds:
        parts.append(f"{cmds} comando(s)")
    return "mexeu em " + " · ".join(parts) if parts else "trabalho concluído"


def handle_post_tool(inp, url, key, owner):
    tool = inp.get("tool_name", "")
    if tool not in WORK_TOOLS:
        return  # leitura/Q&A não conta
    sid = inp.get("session_id", "")
    cwd = inp.get("cwd", "")
    ti = inp.get("tool_input") or {}
    fpath = ti.get("file_path") or ti.get("notebook_path")
    os.makedirs(STATE_DIR, exist_ok=True)
    sp = _state_path(sid)
    host = socket.gethostname()

    if os.path.exists(sp):
        st = json.load(open(sp))
    else:
        # 1º trabalho do turno → cria a work_session "fazendo" no cockpit.
        # db_sid = chave ÚNICA do turno (sid + epoch). Toda escrita vai pela função
        # worklog_report; o db_sid identifica a linha (sem precisar do id do banco).
        title = _last_user_prompt(inp.get("transcript_path", "")) or f"trabalho no Claude Code ({os.path.basename(cwd) or host})"
        db_sid = f"{sid}:{int(time.time())}"
        st = {"db_sid": db_sid, "title": title, "files": [], "tools": {}, "cwd": cwd, "last_patch": 0}
        try:
            _rpc(url, key, {"p_owner": owner, "p_db_sid": db_sid, "p_status": "fazendo",
                            "p_title": title, "p_host": host, "p_cwd": cwd,
                            "p_files": [], "p_tools": {}})
        except Exception:
            pass

    if fpath and fpath not in st["files"]:
        st["files"].append(fpath)
    st["tools"][tool] = st["tools"].get(tool, 0) + 1

    now = time.time()
    if st.get("db_sid") and (now - st.get("last_patch", 0)) > PATCH_THROTTLE_S:
        try:
            _rpc(url, key, {"p_owner": owner, "p_db_sid": st["db_sid"], "p_status": "fazendo",
                            "p_files": st["files"], "p_tools": st["tools"]})
            st["last_patch"] = now
        except Exception:
            pass
    json.dump(st, open(sp, "w"))


def handle_stop(inp, url, key, owner):
    sid = inp.get("session_id", "")
    sp = _state_path(sid)
    if not os.path.exists(sp):
        return  # turno sem trabalho (Q&A pura) → nada a registrar
    try:
        st = json.load(open(sp))
    except Exception:
        return
    summ = _summary(st.get("files", []), st.get("tools", {}))
    db_sid = st.get("db_sid") or f"{sid}:0"
    # uma chamada finaliza a work_session (concluida + resumo) E joga o evento no feed
    try:
        _rpc(url, key, {
            "p_owner": owner, "p_db_sid": db_sid, "p_status": "concluida",
            "p_title": st.get("title"), "p_summary": summ,
            "p_files": st.get("files", []), "p_tools": st.get("tools", {}),
            "p_event": f"✅ {st.get('title','trabalho')[:80]} — {summ}"})
    except Exception:
        pass
    try:
        os.remove(sp)
    except Exception:
        pass


def main():
    try:
        inp = json.load(sys.stdin)
    except Exception:
        return
    url, key, owner = _load_env()
    if not (url and key and owner):
        return  # não configurado nesta máquina → no-op silencioso
    try:
        ev = inp.get("hook_event_name", "")
        if ev == "PostToolUse":
            handle_post_tool(inp, url, key, owner)
        elif ev == "Stop":
            handle_stop(inp, url, key, owner)
    except Exception:
        pass  # hook JAMAIS quebra a sessão


if __name__ == "__main__":
    main()
    sys.exit(0)
