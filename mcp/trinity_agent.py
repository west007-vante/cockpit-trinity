#!/usr/bin/env python3
"""Trinity Agent Connector — conecta um agente REAL da máquina do sócio ao Cockpit.

Roda na M1 do sócio. Faz 2 coisas:
  1) HEARTBEAT: marca o agente como ONLINE no cockpit (a cada 25s). Parou -> some.
  2) Expõe tools MCP pro Claude Code CLI reportar trabalho REAL:
       - report_progress(task_id, progress, status)  -> move a barra da tarefa (e a oferta anda sozinha)
       - log_activity(kind, message)                 -> aparece no feed de atividade do Cockpit
       - chat_reply(conversation_id, body)           -> o agente responde no chat
       - register(name, role)                        -> registra/atualiza o agente (aparece na aba Agentes)

Config por env (cada sócio tem o seu .env gerado pela aba MCP do Cockpit):
  TRINITY_URL          = https://<projeto>.supabase.co
  TRINITY_SERVICE_KEY  = <service key>   (fica SÓ local, nunca no front)
  TRINITY_AGENT_ID     = goggins | rico | steve | <subagente>
  TRINITY_OWNER        = goggins | rico | steve
  TRINITY_AGENT_NAME   = Goggins
  TRINITY_AGENT_ROLE   = Criação de conteúdo em massa

Uso:
  python3 trinity_agent.py            # sobe o heartbeat + servidor MCP (stdio)
  python3 trinity_agent.py --beat     # só heartbeat (sem MCP), pra testar conexão
"""
import os, sys, json, time, threading, urllib.request, urllib.error

URL = os.environ.get("TRINITY_URL", "").rstrip("/")
KEY = os.environ.get("TRINITY_SERVICE_KEY", "")
AID = os.environ.get("TRINITY_AGENT_ID", "")
OWNER = os.environ.get("TRINITY_OWNER", AID)
NAME = os.environ.get("TRINITY_AGENT_NAME", AID.title())
ROLE = os.environ.get("TRINITY_AGENT_ROLE", "Agente")

def _req(method, path, body=None, params=""):
    if not (URL and KEY):
        raise RuntimeError("Faltam TRINITY_URL / TRINITY_SERVICE_KEY no .env")
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{URL}/rest/v1/{path}{params}", data=data, method=method)
    for h, v in {"apikey": KEY, "Authorization": f"Bearer {KEY}",
                 "Content-Type": "application/json", "Prefer": "return=representation"}.items():
        r.add_header(h, v)
    with urllib.request.urlopen(r, timeout=10) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else None

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

# ── registro + heartbeat: SÓ assim o agente aparece "ativo" no Cockpit ──
def register():
    _req("POST", "cockpit_subagents",
         {"id": AID, "owner": OWNER, "name": NAME, "role": ROLE, "online": True,
          "status": "working", "last_heartbeat": now()},
         params="?on_conflict=id")

def beat():
    try:
        _req("PATCH", "cockpit_subagents", {"online": True, "last_heartbeat": now()},
             params=f"?id=eq.{AID}")
    except Exception as e:
        print(f"[trinity] heartbeat falhou: {e}", file=sys.stderr)

def offline():
    try:
        _req("PATCH", "cockpit_subagents", {"online": False, "status": "idle"}, params=f"?id=eq.{AID}")
    except Exception:
        pass

def heartbeat_loop():
    register()
    while True:
        beat(); time.sleep(25)

# ── tools que o Claude Code CLI chama pra reportar trabalho REAL ──
def report_progress(task_id, progress, status="doing"):
    """Move a barra da tarefa no Cockpit. progress 0-100. NÃO é fake: só você (o agente) escreve isso."""
    _req("PATCH", "cockpit_tasks",
         {"progress": int(progress), "status": status, "updated_at": now()},
         params=f"?id=eq.{int(task_id)}")
    return {"ok": True, "task_id": task_id, "progress": progress}

def log_activity(kind, message):
    """Cospe uma linha no feed de atividade ao vivo do Cockpit."""
    _req("POST", "cockpit_events", {"agent_id": OWNER, "kind": kind, "message": message})
    return {"ok": True}

def chat_reply(conversation_id, body):
    """O agente responde numa conversa do chat."""
    _req("POST", "cockpit_messages",
         {"conversation_id": int(conversation_id), "sender": AID, "sender_name": NAME, "body": body})
    return {"ok": True}

def get_tasks():
    """FILA DE EXECUÇÃO do agente: tarefas atribuídas a ele que estão pendentes (todo/doing).
    O agente DEVE executar cada uma e reportar com report_progress. Não pode fugir da fila."""
    rows = _req("GET", "cockpit_tasks",
                params=f"?agent_id=eq.{AID}&status=in.(todo,doing)&order=id&select=id,title,status,progress,offer_id,assignee")
    return {"pending": len(rows or []), "tasks": rows or []}

# ── MCP server (stdio, JSON-RPC) ──
TOOLS = [
    {"name": "report_progress", "description": "Atualiza o progresso (0-100) e status de uma tarefa do Cockpit. Use quando avançar/concluir trabalho REAL.",
     "inputSchema": {"type": "object", "properties": {"task_id": {"type": "integer"}, "progress": {"type": "integer"}, "status": {"type": "string", "enum": ["todo", "doing", "review", "done", "blocked"]}}, "required": ["task_id", "progress"]}},
    {"name": "log_activity", "description": "Registra uma atividade no feed ao vivo do Cockpit.",
     "inputSchema": {"type": "object", "properties": {"kind": {"type": "string"}, "message": {"type": "string"}}, "required": ["message"]}},
    {"name": "chat_reply", "description": "Responde uma mensagem no chat do Cockpit.",
     "inputSchema": {"type": "object", "properties": {"conversation_id": {"type": "integer"}, "body": {"type": "string"}}, "required": ["conversation_id", "body"]}},
    {"name": "get_tasks", "description": "Puxa a FILA de tarefas atribuídas a este agente (pendentes). Chame no início do trabalho: o agente deve executar cada tarefa e reportar com report_progress.",
     "inputSchema": {"type": "object", "properties": {}}},
]
DISPATCH = {"report_progress": report_progress, "log_activity": log_activity, "chat_reply": chat_reply, "get_tasks": get_tasks}

def mcp_serve():
    def send(obj): sys.stdout.write(json.dumps(obj) + "\n"); sys.stdout.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        mid, method = msg.get("id"), msg.get("method")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05",
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "trinity-agent", "version": "1.0"}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            n = msg["params"]["name"]; args = msg["params"].get("arguments", {})
            try:
                out = DISPATCH[n](**args)
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": json.dumps(out)}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": f"erro: {e}"}], "isError": True}})
        elif mid is not None:
            send({"jsonrpc": "2.0", "id": mid, "result": {}})

if __name__ == "__main__":
    if not (URL and KEY and AID):
        print("Faltam env: TRINITY_URL, TRINITY_SERVICE_KEY, TRINITY_AGENT_ID. Pega na aba MCP do Cockpit.", file=sys.stderr)
        sys.exit(1)
    import atexit; atexit.register(offline)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    if "--beat" in sys.argv:
        print(f"[trinity] {NAME} ONLINE no Cockpit (heartbeat a cada 25s). Ctrl+C pra sair.", file=sys.stderr)
        try:
            while True: time.sleep(60)
        except KeyboardInterrupt:
            offline()
    else:
        mcp_serve()
