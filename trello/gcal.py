#!/usr/bin/env python3
"""Google Agenda em stdlib pura — sem pip, sem venv, sem biblioteca do Google.

Por que na mão: este código roda em daemon numa máquina que não é servidor. Uma
dependência a mais é uma coisa a mais pra quebrar às 3 da manhã. urllib resolve.

⚠️  EU NÃO FAÇO LOGIN. O passo de autorizar é do dono da conta, sempre. O que este
    arquivo faz é abrir o navegador na tela certa, escutar a resposta numa porta
    local e guardar o refresh token com chmod 600.

Escopo pedido: calendar.events — SÓ criar/editar evento. Não lê e-mail, não lê
contato, não mexe em Drive. É o menor escopo que faz o trabalho.

    python3 gcal.py --conectar      # a autorização (uma vez, você clica)
    python3 gcal.py --conferir      # mostra as agendas e prova que funciona
    python3 gcal.py --teste         # cria um evento de teste daqui a 1h
"""
import http.server
import json
import os
import socket
import ssl
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

ENV = os.path.expanduser("~/.steve/gcal.env")
SEGREDO = os.path.expanduser("~/.steve/gcal_client.json")
ESCOPO = "https://www.googleapis.com/auth/calendar.events"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"


def _env(arquivo=ENV):
    cfg = {}
    if os.path.exists(arquivo):
        for ln in open(arquivo, encoding="utf-8"):
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, _, v = ln.partition("=")
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return cfg


def _gravar(chave, valor, arquivo=ENV):
    linhas, achou = [], False
    if os.path.exists(arquivo):
        linhas = open(arquivo, encoding="utf-8").read().splitlines()
    for i, ln in enumerate(linhas):
        if ln.strip().startswith(chave + "="):
            linhas[i] = f"{chave}={valor}"
            achou = True
    if not achou:
        linhas.append(f"{chave}={valor}")
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    with open(arquivo, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")
    os.chmod(arquivo, 0o600)


class GCalErro(Exception):
    """Falha traduzida — mensagem que diz o que fazer, não stack trace."""


def _porta_livre():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _ler_client_json():
    """Aceita o JSON que o Google Cloud baixa (formato 'installed')."""
    if not os.path.exists(SEGREDO):
        raise GCalErro(
            f"não achei {SEGREDO}.\n"
            "   Baixe o JSON da credencial 'App para computador' no Google Cloud\n"
            "   e salve nesse caminho. O passo a passo está em:\n"
            "   ~/trinity/trello/GOOGLE-AGENDA.md")
    d = json.load(open(SEGREDO, encoding="utf-8"))
    d = d.get("installed") or d.get("web") or d
    cid, cs = d.get("client_id"), d.get("client_secret")
    if not cid or not cs:
        raise GCalErro(f"{SEGREDO} não tem client_id/client_secret. "
                       "Baixou o arquivo certo? Tem que ser do tipo 'App para computador'.")
    return cid, cs


def conectar():
    """A autorização. Abre o navegador; QUEM clica é o dono da conta."""
    cid, cs = _ler_client_json()
    porta = _porta_livre()
    redirect = f"http://localhost:{porta}"
    p = {"client_id": cid, "redirect_uri": redirect, "response_type": "code",
         "scope": ESCOPO, "access_type": "offline", "prompt": "consent"}
    url = AUTH + "?" + urllib.parse.urlencode(p)

    recebido = {}

    class Mao(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            recebido.update({k: v[0] for k, v in q.items()})
            ok = "code" in recebido
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(("<html><body style='font-family:system-ui;padding:3rem'>"
                              + ("<h2>✅ Autorizado.</h2><p>Pode fechar e voltar pro terminal.</p>"
                                 if ok else
                                 f"<h2>❌ Não autorizou.</h2><p>{recebido.get('error','')}</p>")
                              + "</body></html>").encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", porta), Mao)
    threading.Thread(target=srv.handle_request, daemon=True).start()

    print(f"""
─────────────────────────────────────────────────────────────────────
  Vou abrir o navegador. VOCÊ autoriza — eu não faço login por você.

  Confira na tela: tem que estar pedindo só acesso a EVENTOS DE AGENDA.
  Se pedir e-mail ou contatos, cancele e me chame.

  Se o navegador não abrir sozinho, cole este endereço nele:

  {url}
─────────────────────────────────────────────────────────────────────
""")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print("  esperando você autorizar…")
    srv.server_close()

    if "code" not in recebido:
        raise GCalErro(f"não veio autorização de volta ({recebido.get('error','cancelado')}).")

    corpo = urllib.parse.urlencode({
        "code": recebido["code"], "client_id": cid, "client_secret": cs,
        "redirect_uri": redirect, "grant_type": "authorization_code"}).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(TOKEN, data=corpo), timeout=20) as r:
            tok = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise GCalErro(f"o Google recusou a troca do código: {e.read().decode()[:300]}")

    if not tok.get("refresh_token"):
        raise GCalErro("o Google não mandou refresh_token. Isso acontece quando a conta "
                       "já autorizou antes: revogue em myaccount.google.com/permissions "
                       "e rode de novo.")
    _gravar("GCAL_CLIENT_ID", cid)
    _gravar("GCAL_CLIENT_SECRET", cs)
    _gravar("GCAL_REFRESH_TOKEN", tok["refresh_token"])
    print(f"✅ conectado. Guardado em {ENV} (chmod 600)")
    return True


class GCal:
    def __init__(self):
        c = _env()
        self.cid = c.get("GCAL_CLIENT_ID")
        self.cs = c.get("GCAL_CLIENT_SECRET")
        self.rt = c.get("GCAL_REFRESH_TOKEN")
        self.agenda = c.get("GCAL_AGENDA", "primary")
        if not self.rt:
            raise GCalErro("Google Agenda não conectado. Rode: python3 gcal.py --conectar")
        self._token = None

    def _acesso(self):
        if self._token:
            return self._token
        corpo = urllib.parse.urlencode({
            "client_id": self.cid, "client_secret": self.cs,
            "refresh_token": self.rt, "grant_type": "refresh_token"}).encode()
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(TOKEN, data=corpo), timeout=20) as r:
                self._token = json.loads(r.read().decode())["access_token"]
        except urllib.error.HTTPError as e:
            raise GCalErro(
                "o Google recusou renovar o acesso — a autorização foi revogada? "
                f"Rode de novo: python3 gcal.py --conectar  ({e.read().decode()[:200]})")
        return self._token

    def _chamar(self, metodo, caminho, corpo=None, **params):
        url = f"{API}{caminho}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(corpo).encode() if corpo is not None else None
        cab = {"Authorization": f"Bearer {self._acesso()}"}
        if data:
            cab["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, data=data, headers=cab, method=metodo),
                    timeout=20) as r:
                bruto = r.read().decode()
                return json.loads(bruto) if bruto.strip() else None
        except urllib.error.HTTPError as e:
            raise GCalErro(f"{metodo} {caminho} → HTTP {e.code}: {e.read().decode()[:250]}")

    def agendas(self):
        return (self._chamar("GET", "/users/me/calendarList") or {}).get("items", [])

    def eventos(self, inicio_iso, fim_iso, agenda=None):
        r = self._chamar("GET", f"/calendars/{urllib.parse.quote(agenda or self.agenda)}/events",
                         timeMin=inicio_iso, timeMax=fim_iso, singleEvents="true",
                         orderBy="startTime", maxResults=250)
        return (r or {}).get("items", [])

    def criar_evento(self, titulo, inicio_iso, fim_iso, desc="", url_card=None,
                     agenda=None, alarme_min=10):
        corpo = {
            "summary": titulo,
            "description": (desc + (f"\n\n{url_card}" if url_card else "")).strip(),
            "start": {"dateTime": inicio_iso, "timeZone": "America/Sao_Paulo"},
            "end": {"dateTime": fim_iso, "timeZone": "America/Sao_Paulo"},
            "reminders": {"useDefault": False,
                          "overrides": [{"method": "popup", "minutes": alarme_min}]},
            "source": {"title": "O QUADRO", "url": url_card} if url_card else None,
        }
        corpo = {k: v for k, v in corpo.items() if v is not None}
        return self._chamar("POST", f"/calendars/{urllib.parse.quote(agenda or self.agenda)}/events",
                            corpo)

    def apagar_evento(self, evento_id, agenda=None):
        return self._chamar("DELETE",
                            f"/calendars/{urllib.parse.quote(agenda or self.agenda)}/events/{evento_id}")


if __name__ == "__main__":
    try:
        if "--conectar" in sys.argv:
            conectar()
        elif "--teste" in sys.argv:
            from datetime import datetime, timedelta
            g = GCal()
            i = datetime.now().astimezone() + timedelta(hours=1)
            f = i + timedelta(minutes=30)
            ev = g.criar_evento("🧪 teste do QUADRO — pode apagar",
                                i.isoformat(), f.isoformat(),
                                "Se você está vendo isso, a agenda funciona.")
            print(f"✅ evento criado: {ev.get('htmlLink')}")
            print(f"   (apague com: python3 gcal.py --apagar {ev.get('id')})")
        elif "--apagar" in sys.argv:
            GCal().apagar_evento(sys.argv[sys.argv.index("--apagar") + 1])
            print("✅ apagado")
        else:
            g = GCal()
            print("agendas desta conta:")
            for a in g.agendas():
                marca = " ← padrão" if a.get("primary") else ""
                print(f"  · {a.get('summary')}  [{a.get('id')}]{marca}")
            print(f"\nusando: {g.agenda}")
            print("(pra mudar: GCAL_AGENDA=<id> em ~/.steve/gcal.env)")
    except GCalErro as e:
        print(f"❌ {e}")
        sys.exit(1)
