#!/usr/bin/env python3
"""EXPORTAR SESSÃO — transforma um transcript do Claude Code em markdown legível,
já passado pela FAXINA (sem chave, sem senha, sem token).

É o que atravessa a ponte quando alguém quer abrir uma sessão "por completo".

Uso:
    python3 exportar_sessao.py <arquivo.jsonl>            # imprime o markdown
    python3 exportar_sessao.py <arquivo.jsonl> --resumo   # só as estatísticas
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from faxina import limpar  # noqa: E402

# ferramentas cujo conteúdo não vale a pena despejar no markdown
BARULHENTAS = {"TodoWrite", "Read", "Glob", "Grep", "ListAgents"}
LIMITE_SAIDA = 1200      # corta saída de ferramenta gigante


def _texto(content):
    """Extrai o texto humano de um bloco de mensagem."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    partes = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            partes.append(b.get("text", ""))
    return "\n".join(partes)


def _e_injecao(t):
    """Texto que o harness injeta no turno — não é fala da pessoa."""
    if not t:
        return True
    baixo = t.lstrip().lower()
    return (baixo.startswith("<") or "<system-reminder>" in baixo
            or baixo.startswith("base directory for this skill")
            or baixo.startswith("caveat:"))


def exportar(caminho):
    linhas, ferramentas, n_user, n_assist = [], {}, 0, 0
    inicio = fim = None

    for ln in open(caminho, encoding="utf-8", errors="replace"):
        try:
            ev = json.loads(ln)
        except Exception:
            continue

        ts = ev.get("timestamp")
        if ts:
            inicio = inicio or ts
            fim = ts

        tipo = ev.get("type")
        msg = ev.get("message") or {}

        if tipo == "user":
            conteudo = msg.get("content")
            # tool_result não é fala da pessoa
            if isinstance(conteudo, list) and any(
                    isinstance(b, dict) and b.get("type") == "tool_result" for b in conteudo):
                continue
            t = _texto(conteudo).strip()
            if _e_injecao(t):
                continue
            n_user += 1
            linhas.append(f"\n### 🗣️ Pyerri\n\n{t}\n")

        elif tipo == "assistant":
            conteudo = msg.get("content") or []
            if not isinstance(conteudo, list):
                continue
            fala = _texto(conteudo).strip()
            usos = [b for b in conteudo if isinstance(b, dict) and b.get("type") == "tool_use"]
            if fala:
                n_assist += 1
                linhas.append(f"\n### 🤖 Steve\n\n{fala}\n")
            for u in usos:
                nome = u.get("name", "?")
                ferramentas[nome] = ferramentas.get(nome, 0) + 1
                if nome in BARULHENTAS:
                    continue
                entrada = u.get("input") or {}
                desc = (entrada.get("description") or entrada.get("command")
                        or entrada.get("file_path") or entrada.get("query")
                        or entrada.get("prompt") or "")
                desc = str(desc)[:LIMITE_SAIDA]
                if desc:
                    linhas.append(f"\n> 🔧 **{nome}** — {desc}\n")

    corpo = "".join(linhas)
    corpo_limpo, mascarados = limpar(corpo)

    def _quando(x):
        try:
            return datetime.fromisoformat(x.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return x or "?"

    topo = [
        f"# Sessão — {os.path.basename(caminho).replace('.jsonl','')}",
        "",
        f"**Quando:** {_quando(inicio)} → {_quando(fim)}  ",
        f"**Trocas:** {n_user} pedidos · {n_assist} respostas  ",
        f"**Ferramentas:** " + (", ".join(f"{k}×{v}" for k, v in
                                sorted(ferramentas.items(), key=lambda x: -x[1])[:10]) or "nenhuma"),
        "",
        f"> 🧽 **Faxina:** {mascarados} segredo(s) mascarado(s) antes de sair da máquina."
        if mascarados else "> 🧽 **Faxina:** nenhum segredo encontrado.",
        "",
        "---",
    ]
    return "\n".join(topo) + corpo_limpo, {
        "pedidos": n_user, "respostas": n_assist,
        "ferramentas": ferramentas, "mascarados": mascarados,
        "inicio": inicio, "fim": fim,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    md, meta = exportar(sys.argv[1])
    if "--resumo" in sys.argv:
        print(json.dumps({**meta, "bytes": len(md.encode())}, ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(md)
