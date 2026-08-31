#!/usr/bin/env python3
"""Cliente REST mínimo do Trello — a mão do robô no quadro.

É a metade "robô" da ligação com o Trello. A outra metade é o MCP oficial
(mcp.trello.com/v1), que só funciona enquanto alguém conversa com o Steve.
Este arquivo é o que faz o quadro se alimentar sozinho, 24h, sem conversa.

Credenciais em ~/.steve/trello.env (nunca no código, nunca no git):
    TRELLO_KEY=...        # chave do Power-Up privado (trello.com/apps/admin)
    TRELLO_TOKEN=...      # token do STEVE (o robô age como Steve, não como Pyerri)
    TRELLO_BOARD_ID=...   # preenchido pelo bootstrap_board.py

Stdlib pura de propósito: este código roda em daemon e dentro de hook. Sem
dependência pra instalar, sem venv pra quebrar.
"""
import json
import os
import time
import urllib.parse
import urllib.request
import urllib.error

ENV_FILE = os.path.expanduser("~/.steve/trello.env")
BASE = "https://api.trello.com/1"
TIMEOUT = 15


class TrelloErro(Exception):
    """Falha da API já traduzida — mensagem legível em vez de stack de urllib."""


def carregar_env(arquivo=ENV_FILE):
    """Lê o .env no mesmo formato do worklog.env. Ambiente tem precedência."""
    cfg = {}
    try:
        if os.path.exists(arquivo):
            for ln in open(arquivo, encoding="utf-8"):
                ln = ln.strip()
                if ln and not ln.startswith("#") and "=" in ln:
                    k, _, v = ln.partition("=")
                    cfg[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    for k in ("TRELLO_KEY", "TRELLO_TOKEN", "TRELLO_BOARD_ID"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


class Trello:
    def __init__(self, key=None, token=None, board_id=None, env=None):
        cfg = env if env is not None else carregar_env()
        self.key = key or cfg.get("TRELLO_KEY")
        self.token = token or cfg.get("TRELLO_TOKEN")
        self.board_id = board_id or cfg.get("TRELLO_BOARD_ID")
        if not self.key or not self.token:
            raise TrelloErro(
                "Falta chave ou token do Trello. Rode:  python3 ~/trinity/trello/destravar.py\n"
                f"(o arquivo esperado é {ENV_FILE})")

    # ---------------------------------------------------------------- transporte
    def _chamar(self, metodo, caminho, params=None, corpo=None, tentativa=1):
        p = dict(params or {})
        p["key"] = self.key
        p["token"] = self.token
        url = f"{BASE}{caminho}?{urllib.parse.urlencode(p, doseq=True)}"
        data = json.dumps(corpo).encode() if corpo is not None else None
        cab = {"Accept": "application/json"}
        if data:
            cab["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=cab, method=metodo)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                bruto = r.read().decode()
                return json.loads(bruto) if bruto.strip() else None
        except urllib.error.HTTPError as e:
            corpo_erro = ""
            try:
                corpo_erro = e.read().decode()[:300]
            except Exception:
                pass
            # 429 = limite de taxa (300 req/10s por chave). Espera e repete.
            if e.code == 429 and tentativa <= 4:
                time.sleep(2 * tentativa)
                return self._chamar(metodo, caminho, params, corpo, tentativa + 1)
            if e.code == 401:
                # O Trello devolve 401 pra chave errada E pra token errado, mas o
                # corpo diz qual. Dizer "o token expirou" quando o problema é a
                # chave manda a pessoa refazer o passo errado.
                cx = corpo_erro.lower()
                if "invalid key" in cx:
                    raise TrelloErro(
                        "401 · invalid key — a CHAVE está errada (não o token).\n"
                        "   A Chave de API tem 32 caracteres. Se a sua tem 64, você colou o\n"
                        "   Segredo: ele fica logo abaixo da chave na tela e nós não usamos ele.")
                if "invalid token" in cx or "expired" in cx:
                    raise TrelloErro(
                        "401 · invalid token — a chave está certa, o TOKEN é que não serve.\n"
                        "   Ele foi revogado, expirou, ou o que você colou não é o token.\n"
                        "   Gere outro pelo link do passo 2.")
                raise TrelloErro(f"401 — o Trello recusou as credenciais. ({corpo_erro})")
            raise TrelloErro(f"{metodo} {caminho} → HTTP {e.code}: {corpo_erro}")
        except urllib.error.URLError as e:
            if tentativa <= 3:
                time.sleep(2 * tentativa)
                return self._chamar(metodo, caminho, params, corpo, tentativa + 1)
            raise TrelloErro(f"{metodo} {caminho} → sem rede: {e.reason}")

    def get(self, caminho, **params):
        return self._chamar("GET", caminho, params)

    def post(self, caminho, **params):
        return self._chamar("POST", caminho, params)

    def put(self, caminho, **params):
        return self._chamar("PUT", caminho, params)

    def delete(self, caminho, **params):
        return self._chamar("DELETE", caminho, params)

    # ------------------------------------------------------------------- quem sou
    def eu(self):
        return self.get("/members/me", fields="id,username,fullName,email")

    def revogar_token(self, token=None):
        """Mata um token. Um token gerado na conta errada não pode ficar vivo:
        ele nasce com escrita em TODO quadro daquela conta e sem prazo pra expirar."""
        alvo = token or self.token
        return self._chamar("DELETE", f"/tokens/{alvo}", {"token": alvo})

    # -------------------------------------------------------------------- quadros
    def criar_board(self, nome, org_id=None, desc=""):
        p = {"name": nome, "desc": desc,
             "defaultLists": "false",      # não queremos To Do/Doing/Done do Trello
             "defaultLabels": "false",     # as etiquetas são as 9 áreas do Quadro da Obra
             "prefs_permissionLevel": "private"}
        if org_id:
            p["idOrganization"] = org_id
        return self.post("/boards/", **p)

    def board(self, board_id=None):
        return self.get(f"/boards/{board_id or self.board_id}",
                        fields="id,name,url,shortUrl,idOrganization")

    def organizacoes(self):
        return self.get("/members/me/organizations", fields="id,displayName,name")

    # --------------------------------------------------------------------- listas
    def listas(self, board_id=None):
        return self.get(f"/boards/{board_id or self.board_id}/lists",
                        fields="id,name,pos,closed", filter="open")

    def criar_lista(self, nome, pos, board_id=None):
        return self.post("/lists", name=nome, idBoard=board_id or self.board_id, pos=pos)

    # ------------------------------------------------------------------ etiquetas
    def etiquetas(self, board_id=None):
        return self.get(f"/boards/{board_id or self.board_id}/labels", limit=200)

    def criar_etiqueta(self, nome, cor, board_id=None):
        return self.post("/labels", name=nome, color=cor,
                         idBoard=board_id or self.board_id)

    # -------------------------------------------------------------------- membros
    def membros(self, board_id=None):
        return self.get(f"/boards/{board_id or self.board_id}/members",
                        fields="id,username,fullName")

    def convidar_por_email(self, email, nome_completo="", board_id=None):
        """Convite é ato do dono do quadro, não criação de conta. Quem aceita é a pessoa."""
        p = {"email": email}
        if nome_completo:
            p["fullName"] = nome_completo
        return self.put(f"/boards/{board_id or self.board_id}/members", **p)

    # ---------------------------------------------------------------------- cards
    def cards_da_lista(self, list_id):
        return self.get(f"/lists/{list_id}/cards",
                        fields="id,name,desc,idList,idLabels,idMembers,due,start,dueComplete,shortUrl,dateLastActivity")

    def cards_do_board(self, board_id=None):
        return self.get(f"/boards/{board_id or self.board_id}/cards",
                        fields="id,name,desc,idList,idLabels,idMembers,due,start,dueComplete,shortUrl,dateLastActivity",
                        filter="open")

    def criar_card(self, list_id, nome, desc="", labels=None, membros=None,
                   start=None, due=None, pos="bottom"):
        p = {"idList": list_id, "name": nome, "desc": desc, "pos": pos}
        if labels:
            p["idLabels"] = ",".join(labels)
        if membros:
            p["idMembers"] = ",".join(membros)
        if start:
            p["start"] = start
        if due:
            p["due"] = due
        return self.post("/cards", **p)

    def atualizar_card(self, card_id, **campos):
        return self.put(f"/cards/{card_id}", **campos)

    def mover_card(self, card_id, list_id, pos="top"):
        return self.put(f"/cards/{card_id}", idList=list_id, pos=pos)

    def arquivar_card(self, card_id):
        return self.put(f"/cards/{card_id}", closed="true")

    def comentar(self, card_id, texto):
        return self.post(f"/cards/{card_id}/actions/comments", text=texto)

    # ------------------------------------------------------------------ checklist
    def checklists(self, card_id):
        return self.get(f"/cards/{card_id}/checklists")

    def criar_checklist(self, card_id, nome="O que falta"):
        return self.post("/checklists", idCard=card_id, name=nome)

    def item_checklist(self, checklist_id, nome, checado=False):
        return self.post(f"/checklists/{checklist_id}/checkItems",
                         name=nome[:16384], checked="true" if checado else "false")

    # --------------------------------------------------------------------- busca
    def buscar_cards(self, termo, board_id=None):
        r = self.get("/search", query=termo, modelTypes="cards", cards_limit=50,
                     idBoards=board_id or self.board_id)
        return (r or {}).get("cards", [])


if __name__ == "__main__":
    # Teste de fumaça: prova que a chave funciona e mostra quem o robô é.
    import sys
    try:
        t = Trello()
        eu = t.eu()
        print(f"✅ conectado como: {eu.get('fullName')} (@{eu.get('username')})")
        if t.board_id:
            b = t.board()
            print(f"   quadro: {b.get('name')} → {b.get('shortUrl')}")
            print(f"   listas: {len(t.listas())} · cards: {len(t.cards_do_board())}")
        else:
            print("   (TRELLO_BOARD_ID ainda vazio — rode o bootstrap_board.py)")
    except TrelloErro as e:
        print(f"❌ {e}")
        sys.exit(1)
