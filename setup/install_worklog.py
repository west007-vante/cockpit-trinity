#!/usr/bin/env python3
"""Instalador do Worklog nativo — faz o Claude Code de cada sócio reportar
trabalho REAL no cockpit Trinity automaticamente (Pendente/Fazendo/Concluída).

Uso (na máquina do sócio):
    python3 install_worklog.py <owner>
  onde <owner> = steve | goggins | rico

Ele:
  1. instala o hook em ~/.steve/worklog_hook.py
  2. escreve ~/.steve/worklog.env (SUPABASE_URL + KEY + TRINITY_OWNER, chmod 600)
     — usa a URL + anon key PÚBLICAS embutidas (o hook só grava no worklog, via RLS
       escopado). Se a máquina tiver um .env do conector, ele tem precedência;
       dá pra forçar com --url/--key. Sócio nenhum precisa receber a service key.
  3. liga os hooks PostToolUse + Stop no ~/.claude/settings.json (idempotente)

Depois: REINICIE o Claude Code. Pronto — todo trabalho (criar/executar) vira
task no cockpit; conversa pura (pergunta/resposta) não gera nada.
"""
import json
import os
import shutil
import sys

HOME = os.path.expanduser("~")
STEVE_DIR = os.path.join(HOME, ".steve")
HOOK_DST = os.path.join(STEVE_DIR, "worklog_hook.py")
ENV_DST = os.path.join(STEVE_DIR, "worklog.env")
SETTINGS = os.path.join(HOME, ".claude", "settings.json")
HOOK_CMD = f'python3 {HOOK_DST}'
WORK_MATCHER = "Write|Edit|MultiEdit|NotebookEdit|Bash"

# URL + anon key PÚBLICAS da Trinity (já públicas no index.html / GitHub Pages —
# seguro embutir). O hook só GRAVA nas tabelas do worklog via policy RLS escopada
# aos 3 sócios; a SERVICE key NUNCA é distribuída pras máquinas dos sócios.
# É o fallback: se a máquina já tiver um .env do conector (ex.: a do Pyerri), ele
# tem precedência. Sócio sem .env nenhum cai aqui e instala sem pedir chave a ninguém.
PUBLIC_URL = "https://fneholznpbjbvdswvuyb.supabase.co"
PUBLIC_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZuZWhvbHpucGJqYnZkc3d2dXliIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc1NDQ2NzEsImV4cCI6MjA5MzEyMDY3MX0."
    "AJMeZwBeI1BuAzSWL36Rk69-nLNW8CE1r9ORzZHNiLk"
)

# locais onde o .env do conector da Trinity costuma estar
ENV_CANDIDATES = [
    ENV_DST,
    os.path.join(HOME, "cockpit-trinity", ".env"),
    os.path.join(HOME, "Dev", "cockpit-trinity", ".env"),
    os.path.join(HOME, "Dev", "steve-backend", ".env"),
]


def _read_env_file(path):
    d = {}
    try:
        for ln in open(path, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, _, v = ln.partition("=")
                d[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return d


def resolve_creds(args):
    url = key = owner = None
    for i, a in enumerate(args):
        if a == "--url" and i + 1 < len(args):
            url = args[i + 1]
        if a == "--key" and i + 1 < len(args):
            key = args[i + 1]
    for path in ENV_CANDIDATES:
        d = _read_env_file(path)
        url = url or d.get("SUPABASE_URL") or d.get("NEXT_PUBLIC_SUPABASE_URL")
        key = key or d.get("SUPABASE_KEY") or d.get("SUPABASE_SERVICE_KEY") or d.get("SUPABASE_SERVICE_ROLE_KEY")
        owner = owner or d.get("TRINITY_OWNER")
        if url and key:
            break
    # fallback público: garante que o sócio NUNCA fica sem chave (e sem service key).
    url = url or PUBLIC_URL
    key = key or PUBLIC_ANON_KEY
    return url, key, owner


def merge_settings(settings_path):
    """Adiciona os hooks sem clobberar nada. Idempotente."""
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    cfg = {}
    if os.path.exists(settings_path):
        try:
            cfg = json.load(open(settings_path, encoding="utf-8"))
        except Exception:
            bak = settings_path + ".bak-worklog"
            shutil.copy(settings_path, bak)
            print(f"  ⚠️ settings.json ilegível — backup em {bak}, recriando hooks")
            cfg = {}
    hooks = cfg.setdefault("hooks", {})

    def ensure(event, matcher):
        arr = hooks.setdefault(event, [])
        # já instalado? (procura nosso comando)
        for entry in arr:
            for h in entry.get("hooks", []):
                if h.get("command") == HOOK_CMD:
                    return False
        block = {"hooks": [{"type": "command", "command": HOOK_CMD}]}
        if matcher:
            block["matcher"] = matcher
        arr.append(block)
        return True

    a = ensure("PostToolUse", WORK_MATCHER)
    b = ensure("Stop", None)
    json.dump(cfg, open(settings_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return a or b


def main():
    args = sys.argv[1:]
    pos = [a for a in args if not a.startswith("--") and a not in ("steve", "goggins", "rico") or a in ("steve", "goggins", "rico")]
    owner_arg = next((a for a in args if a in ("steve", "goggins", "rico")), None)
    if not owner_arg:
        print("uso: python3 install_worklog.py <steve|goggins|rico> [--url URL --key KEY]")
        return 1

    url, key, env_owner = resolve_creds(args)
    owner = owner_arg or env_owner
    using_public = (key == PUBLIC_ANON_KEY)

    os.makedirs(STEVE_DIR, exist_ok=True)
    # 1) hook
    here = os.path.dirname(os.path.abspath(__file__))
    src_hook = os.path.join(here, "worklog_hook.py")
    if os.path.abspath(src_hook) != os.path.abspath(HOOK_DST):
        shutil.copy(src_hook, HOOK_DST)
    # 2) env
    with open(ENV_DST, "w", encoding="utf-8") as f:
        f.write(f"SUPABASE_URL={url}\nSUPABASE_KEY={key}\nTRINITY_OWNER={owner}\n")
    os.chmod(ENV_DST, 0o600)
    # 3) hooks no settings
    changed = merge_settings(SETTINGS)

    print("✅ Worklog instalado.")
    print(f"   • hook:     {HOOK_DST}")
    print(f"   • chave:    {'pública (anon) — escreve só no worklog, escopado' if using_public else 'do .env local'}")
    print(f"   • env:      {ENV_DST}  (owner={owner}, chmod 600)")
    print(f"   • settings: {SETTINGS}  ({'hooks ligados' if changed else 'já estava ligado'})")
    print("\n👉 REINICIE o Claude Code (feche e abra) pra ativar.")
    print("   A partir daí: tudo que você CRIAR/EXECUTAR vira task no cockpit; pergunta/resposta pura não gera nada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
