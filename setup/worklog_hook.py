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
    return _req("POST", f"{url}/rest/v1/rpc/trinity_worklog_report", key, params)


# Coisas que o Claude Code injeta no turno e NÃO são o que a pessoa digitou:
# conteúdo de skill, lembrete de sistema, corpo de slash command. Se isso virar
# título, o worklog mostra tripa interna pro sócio em vez do pedido real.
_LIXO = ("<", "base directory for this skill", "caveat:", "<system-reminder>",
         "<command-name>", "<command-message>", "the user opened the file")


def _e_prompt_humano(text):
    if not text:
        return False
    t = text.lstrip().lower()
    if any(t.startswith(p) for p in _LIXO):
        return False
    if "<system-reminder>" in t or "base directory for this skill" in t:
        return False
    # Era 600 e comia pedido longo: o Pyerri dita parágrafos inteiros, e o turno
    # ficava com o título genérico "trabalho no Claude Code". Agora aceita o pedido
    # comprido e quem corta é o _encurtar — rejeitar por tamanho perdia o título real.
    return len(text) <= 6000


def _encurtar(t, n=120):
    t = " ".join((t or "").split())          # tira quebra de linha e espaço duplo
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


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
            if _e_prompt_humano(text):
                title = text
        return _encurtar(title)
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


# ---------------------------------------------------------------------------
# A FILA DO QUADRO (acrescentado em 30/08/2026)
#
# O worklog manda o trabalho pro Supabase (a Ponte com o Davi). O quadro do
# Trello é alimentado por esta fila local, consumida pelo roteador.
#
# Por que uma fila local em vez de ler o Supabase de volta: a chave que o hook
# tem SÓ ESCREVE (a leitura é negada de propósito — furo fechado em 29/08). Ler
# de volta exigiria credencial nova e mais poderosa na máquina. A fila resolve
# sem abrir nada: cada lado alimenta o mesmo quadro do Trello, e o Trello é o
# ponto de encontro. Funciona offline; o roteador consome quando puder.
# ---------------------------------------------------------------------------
FILA = os.path.join(STATE_DIR, "fila.jsonl")
LEITURA_TOOLS = {"Read", "Grep", "Glob", "WebSearch", "WebFetch", "NotebookRead"}


def _enfileirar(reg):
    """Acrescenta uma linha na fila. Falha aqui NUNCA pode derrubar a sessão."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(FILA, "a", encoding="utf-8") as f:
            f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _medir_turno(transcript_path):
    """Mede o ÚLTIMO turno do transcript: duração, ferramentas usadas e título.

    Serve à regra da Bancada: um turno só de pesquisa (leu, buscou, não escreveu)
    que passe do tempo mínimo vira card de curiosidade. Um 'que horas são' não.
    """
    ferramentas, t0, t1, titulo = {}, None, None, ""
    try:
        eventos = []
        for ln in open(transcript_path, encoding="utf-8", errors="ignore"):
            try:
                eventos.append(json.loads(ln))
            except Exception:
                continue
        # acha onde começou o último turno humano
        inicio = 0
        for i, ev in enumerate(eventos):
            if ev.get("type") != "user":
                continue
            c = (ev.get("message") or {}).get("content")
            txt = c if isinstance(c, str) else " ".join(
                b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"
            ) if isinstance(c, list) and not any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in c) else ""
            if _e_prompt_humano(txt):
                inicio, titulo = i, txt
        for ev in eventos[inicio:]:
            ts = ev.get("timestamp")
            if ts:
                t0 = t0 or ts
                t1 = ts
            msg = ev.get("message") or {}
            for b in (msg.get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    n = b.get("name", "")
                    ferramentas[n] = ferramentas.get(n, 0) + 1
    except Exception:
        pass
    dur = 0
    if t0 and t1:
        try:
            from datetime import datetime
            a = datetime.fromisoformat(str(t0).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(t1).replace("Z", "+00:00"))
            dur = max(0, int((b - a).total_seconds()))
        except Exception:
            pass
    return dur, ferramentas, _encurtar(titulo)


def _bancada(inp, owner):
    """Turno SEM trabalho: decide se foi estudo (vira card) ou conversa (morre).

    Esta é a única mudança de comportamento no filtro do Pyerri. Antes, TODO turno
    sem escrita era descartado — inclusive uma hora de estudo. A regra nova exige
    tempo E busca de verdade, então conversa fiada continua morrendo.
    """
    dur, fer, titulo = _medir_turno(inp.get("transcript_path", ""))
    buscas = sum(v for k, v in fer.items() if k in LEITURA_TOOLS)
    if dur < 300 or buscas < 2 or not titulo:
        return                                  # conversa. Morre aqui, como sempre.
    _enfileirar({
        "db_sid": f"{inp.get('session_id','')}:{int(time.time())}",
        "owner": owner, "title": titulo, "files": [], "tools": fer,
        "cwd": inp.get("cwd", ""), "duracao_s": dur, "escreveu": False,
        "fim": int(time.time()), "origem": "pesquisa",
    })


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
        st = {"db_sid": db_sid, "title": title, "files": [], "tools": {}, "cwd": cwd,
              "last_patch": 0, "inicio": time.time()}
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
        # Turno sem escrita. Antes morria aqui sempre. Agora ainda morre se foi
        # conversa — mas se foi estudo de verdade, vira card na Bancada.
        _bancada(inp, owner)
        return
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
    # A fila do quadro. Independente do Supabase de propósito: se a Ponte estiver
    # fora do ar, o card ainda nasce. São dois destinos, não um encadeado.
    _enfileirar({
        "db_sid": db_sid, "owner": owner, "title": st.get("title"),
        "files": st.get("files", []), "tools": st.get("tools", {}),
        "cwd": st.get("cwd", ""), "resumo": summ, "escreveu": True,
        "duracao_s": max(0, int(time.time() - st.get("inicio", time.time()))),
        "fim": int(time.time()), "origem": "trabalho",
    })
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
    if not owner:
        return  # não configurado nesta máquina → no-op silencioso
    # Supabase fora do ar ou não configurado NÃO pode matar a fila do quadro:
    # os dois destinos são independentes. Sem url/key, o worklog vira no-op e a
    # fila do Trello continua enchendo — o card nasce igual.
    url = url or ""
    key = key or ""
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
