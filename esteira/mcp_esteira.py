#!/usr/bin/env python3
"""O MCP DA CASA — o Claude Code de cada sócio conversa com a plataforma.

Servidor MCP por STDIO (JSON-RPC 2.0, uma mensagem por linha) — stdlib pura,
nenhuma porta aberta. Cada sócio instala na própria máquina:

    claude mcp add esteira --scope user -- python3 ~/esteira/mcp_esteira.py

A credencial local (~/.steve/esteira.env, gerada no painel) autentica as
chamadas ao banco compartilhado. Sem credencial, as ferramentas de banco
explicam o caminho em vez de quebrar.

O que o agente ganha:
  quadro_listar / card_criar        o quadro do Trello, sem sair da conversa
  fluxo_listar / fluxo_rodar        os fluxos da ESTEIRA (rodar = ENSAIO por
                                    padrão; valendo só se o fluxo estiver solto)
  recado_deixar                     pedir algo pro agente de outro sócio
  memoria_comum_ler / _gravar       a memória que os três dividem
"""
import json
import os
import sys
import traceback

CASA = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, CASA)
LOG = os.path.join(CASA, "mcp.log")


def _log(*a):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(" ".join(str(x) for x in a) + "\n")
    except Exception:
        pass


FERRAMENTAS = [
    {"name": "quadro_listar",
     "description": "Lista os cartões do quadro do Trello (O QUADRO · Pyerri × Davi). "
                    "Opcionalmente filtra por lista (ex.: '🗓️ Hoje', '🔨 Fazendo').",
     "inputSchema": {"type": "object", "properties": {
         "lista": {"type": "string", "description": "nome exato da lista (opcional)"}}}},
    {"name": "card_criar",
     "description": "Cria um cartão no quadro. O cartão sai carimbado com quem criou.",
     "inputSchema": {"type": "object", "properties": {
         "titulo": {"type": "string"},
         "lista": {"type": "string", "description": "padrão: 📥 Entrada"},
         "descricao": {"type": "string"}},
         "required": ["titulo"]}},
    {"name": "fluxo_listar",
     "description": "Lista os fluxos da ESTEIRA: os desta máquina e os compartilhados no banco.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "fluxo_rodar",
     "description": "Roda um fluxo da ESTEIRA. SEMPRE em ensaio por padrão (mostra o que "
                    "faria sem fazer). valendo=true só funciona se o dono da máquina soltou o fluxo.",
     "inputSchema": {"type": "object", "properties": {
         "nome": {"type": "string"},
         "valendo": {"type": "boolean", "default": False}},
         "required": ["nome"]}},
    {"name": "recado_deixar",
     "description": "Deixa um recado na fila compartilhada pro agente de outro sócio "
                    "(steve, rico ou joao) executar na máquina dele.",
     "inputSchema": {"type": "object", "properties": {
         "para": {"type": "string", "enum": ["steve", "rico", "joao"]},
         "mensagem": {"type": "string"}},
         "required": ["para", "mensagem"]}},
    {"name": "memoria_comum_ler",
     "description": "Lê as últimas anotações da memória que os três sócios dividem.",
     "inputSchema": {"type": "object", "properties": {
         "quantas": {"type": "integer", "default": 10}}}},
    {"name": "memoria_comum_gravar",
     "description": "Grava uma anotação na memória comum dos três sócios.",
     "inputSchema": {"type": "object", "properties": {
         "titulo": {"type": "string"}, "corpo": {"type": "string"}},
         "required": ["titulo", "corpo"]}},
]


# ─────────────────────────────────────────────────────── as ferramentas
def t_quadro_listar(args):
    sys.path.insert(0, os.path.expanduser("~/trinity/trello"))
    from trello_api import Trello
    from comum import Indice
    t = Trello()
    idx = Indice(t)
    filtro = (args.get("lista") or "").strip()
    linhas = []
    for c in idx.cards():
        lista = idx.listas_por_id.get(c.get("idList"), "?")
        if filtro and lista != filtro:
            continue
        linhas.append(f"[{lista}] {c.get('name')}")
    return "\n".join(linhas) or "(nenhum cartão" + (f" em {filtro})" if filtro else ")")


def t_card_criar(args):
    os.environ.setdefault("TRELLO_ASSINATURA", "mcp-esteira")
    sys.path.insert(0, os.path.expanduser("~/trinity/trello"))
    from trello_api import Trello
    from comum import Indice
    t = Trello()
    idx = Indice(t)
    lista = args.get("lista") or "📥 Entrada"
    c = t.criar_card(idx.lista(lista), args["titulo"], args.get("descricao") or "")
    return f"criado: {c.get('name')} → {c.get('shortUrl')}"


def t_fluxo_listar(args):
    import guarda
    locais = []
    fdir = os.path.join(CASA, "fluxos")
    for f in sorted(os.listdir(fdir)) if os.path.isdir(fdir) else []:
        if f.endswith(".json"):
            try:
                d = json.load(open(os.path.join(fdir, f), encoding="utf-8"))
                estado = "🎭 ensaio" if guarda.em_ensaio(d) else "▶️ solto"
                locais.append(f"  {estado}  {d.get('nome', f)}  ({len(d.get('nos', []))} nós)")
            except Exception:
                pass
    out = "NESTA MÁQUINA:\n" + ("\n".join(locais) or "  (nenhum)")
    try:
        import banco
        comp = banco.fluxos_listar()
        out += "\n\nCOMPARTILHADOS NO BANCO:\n" + ("\n".join(
            f"  {f['nome']} (dono {f['dono']}, editado por {f['editado_por']})"
            for f in comp) or "  (nenhum)")
    except Exception as e:
        out += f"\n\n(banco indisponível: {e})"
    return out


def t_fluxo_rodar(args):
    import guarda
    import motor
    nome = str(args.get("nome", "")).replace(".json", "")
    caminho = os.path.join(CASA, "fluxos", os.path.basename(nome) + ".json")
    if not os.path.exists(caminho):
        return f"o fluxo '{nome}' não existe nesta máquina. fluxo_listar mostra os que existem."
    fluxo = json.load(open(caminho, encoding="utf-8"))
    quer_valendo = bool(args.get("valendo"))
    pode, modo, recados = guarda.liberado_pra_rodar(fluxo, forcar_ensaio=not quer_valendo)
    linhas = list(recados)
    if not pode:
        return "\n".join(linhas)
    out = motor.rodar(fluxo, modo)
    for nid, r in out["resultado"].items():
        linhas.append(f"{'✅' if r.get('ok') else '❌'} {nid}: {(r.get('saida') or '')[:300]}")
    linhas.append(f"— {out['executados']} nó(s) · diário execucoes/{out['diario']}.jsonl")
    return "\n".join(linhas)


def t_recado_deixar(args):
    import banco
    rid = banco.recado_deixar(args["para"], "mensagem", {"mensagem": args["mensagem"]})
    return (f"recado #{rid} deixado pra {args['para']}. O daemon da máquina dele puxa "
            f"em até 30 s quando estiver ligado.")


def t_memoria_comum_ler(args):
    import banco
    ms = banco.memoria_ler(int(args.get("quantas") or 10))
    return "\n".join(f"[{m['autor']} · {m['criado_em'][:10]}] {m['titulo']}\n  {m['corpo'][:300]}"
                     for m in ms) or "(a memória comum está vazia)"


def t_memoria_comum_gravar(args):
    import banco
    mid = banco.memoria_gravar(args["titulo"], args["corpo"])
    return f"gravado na memória comum (#{mid}). Os três enxergam."


EXEC = {"quadro_listar": t_quadro_listar, "card_criar": t_card_criar,
        "fluxo_listar": t_fluxo_listar, "fluxo_rodar": t_fluxo_rodar,
        "recado_deixar": t_recado_deixar, "memoria_comum_ler": t_memoria_comum_ler,
        "memoria_comum_gravar": t_memoria_comum_gravar}


# ──────────────────────────────────────────────── o laço JSON-RPC (stdio)
def responder(rid, resultado=None, erro=None):
    msg = {"jsonrpc": "2.0", "id": rid}
    if erro:
        msg["error"] = erro
    else:
        msg["result"] = resultado
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    _log("=== mcp_esteira subiu ===")
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            req = json.loads(linha)
        except Exception:
            continue
        metodo, rid = req.get("method"), req.get("id")
        try:
            if metodo == "initialize":
                versao = (req.get("params") or {}).get("protocolVersion") or "2024-11-05"
                responder(rid, {"protocolVersion": versao,
                                "capabilities": {"tools": {}},
                                "serverInfo": {"name": "esteira", "version": "2.0"}})
            elif metodo == "notifications/initialized":
                pass                        # notificação — sem resposta
            elif metodo == "ping":
                responder(rid, {})
            elif metodo == "tools/list":
                responder(rid, {"tools": FERRAMENTAS})
            elif metodo == "tools/call":
                p = req.get("params") or {}
                nome = p.get("name")
                fn = EXEC.get(nome)
                if not fn:
                    responder(rid, {"content": [{"type": "text",
                               "text": f"ferramenta desconhecida: {nome}"}], "isError": True})
                else:
                    try:
                        texto = fn(p.get("arguments") or {})
                        responder(rid, {"content": [{"type": "text", "text": str(texto)[:20000]}]})
                    except Exception as e:
                        _log("erro em", nome, ":", traceback.format_exc())
                        responder(rid, {"content": [{"type": "text",
                                   "text": f"não deu: {e}"}], "isError": True})
            elif rid is not None:
                responder(rid, erro={"code": -32601, "message": f"método desconhecido: {metodo}"})
        except Exception:
            _log("erro geral:", traceback.format_exc())


if __name__ == "__main__":
    main()
