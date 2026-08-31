#!/usr/bin/env python3
"""A PONTE — serve o canvas e faz o meio de campo. Stdlib pura.

Por que existe, em vez de um HTML solto:

  1. A CHAVE MORA AQUI. Se o token do Trello estivesse dentro do .html, qualquer
     um que abrisse o arquivo teria escrita no quadro. O navegador recebe os
     cartões já prontos e nunca vê credencial nenhuma.
  2. O NAVEGADOR NÃO EXECUTA NADA. Ele PEDE; quem roda é o motor, deste lado,
     depois de passar pelo guarda.
  3. Só escuta em 127.0.0.1 — nada de fora da máquina alcança.

    python3 servidor.py            # porta 7717
    python3 servidor.py --porta 8080
"""
import json
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda   # noqa: E402
import motor    # noqa: E402
import gatilhos   # noqa: E402
import terminais  # noqa: E402

CASA = os.path.dirname(os.path.abspath(__file__))
FLUXOS = os.path.join(CASA, "fluxos")
PORTA_PADRAO = 7717

_cache = {"quadro": None, "quando": 0}
_rodando = {}          # nome do fluxo → estado da rodada em curso


def cartoes_do_quadro(forcar=False):
    """Os cartões de verdade, do Trello. Cache curto: o canvas pede a cada
    recarga e não faz sentido martelar a API por isso."""
    if not forcar and _cache["quadro"] and time.time() - _cache["quando"] < 45:
        return _cache["quadro"]
    try:
        sys.path.insert(0, os.path.expanduser("~/trinity/trello"))
        from trello_api import Trello
        from comum import Indice
        from cartao import id_do_nome, ler_desc
        t = Trello()
        idx = Indice(t)
        listas = {l["id"]: l["name"] for l in t.listas()}
        etq = {e["id"]: e.get("name") for e in (t.etiquetas() or [])}
        out = []
        for c in idx.cards():
            d = ler_desc(c.get("desc")) or {}
            out.append({
                "id": c["id"],
                "tid": id_do_nome(c.get("name")) or d.get("id"),
                "nome": c.get("name"),
                "lista": listas.get(c.get("idList"), "?"),
                "etiquetas": [etq.get(i) for i in (c.get("idLabels") or []) if etq.get(i)],
                "area": d.get("area"), "e": d.get("e"), "peso": d.get("peso"),
                "url": c.get("shortUrl"),
            })
        _cache.update(quadro={"ok": True, "cartoes": out, "listas": list(listas.values())},
                      quando=time.time())
    except Exception as e:
        _cache.update(quadro={"ok": False, "erro": str(e), "cartoes": [], "listas": []},
                      quando=time.time())
    return _cache["quadro"]


def listar_fluxos():
    os.makedirs(FLUXOS, exist_ok=True)
    out = []
    for f in sorted(os.listdir(FLUXOS)):
        if not f.endswith(".json"):
            continue
        try:
            d = json.load(open(os.path.join(FLUXOS, f), encoding="utf-8"))
            out.append({"arquivo": f, "nome": d.get("nome", f[:-5]),
                        "nos": len(d.get("nos", [])), "fios": len(d.get("fios", [])),
                        "ensaio": guarda.em_ensaio(d),
                        "gatilho": (d.get("gatilho") or {}).get("tipo", "manual")})
        except Exception as e:
            out.append({"arquivo": f, "nome": f[:-5], "erro": str(e)})
    return out


def caminho_fluxo(nome):
    """Só nome de arquivo, nunca caminho — senão dava pra escrever em qualquer lugar."""
    limpo = os.path.basename(str(nome)).replace("..", "")
    if not limpo.endswith(".json"):
        limpo += ".json"
    return os.path.join(FLUXOS, limpo)


class Mao(BaseHTTPRequestHandler):
    def _responder(self, obj, codigo=200):
        corpo = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _arquivo(self, caminho, mime):
        try:
            corpo = open(caminho, "rb").read()
        except FileNotFoundError:
            self.send_error(404, "não achei o arquivo")
            return
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _corpo_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    # ─────────────────────────────────────────────────────────────── GET
    def do_GET(self):
        rota = urllib.parse.urlparse(self.path)
        p = rota.path
        q = urllib.parse.parse_qs(rota.query)

        if p in ("/", "/index.html", "/esteira.html"):
            return self._arquivo(os.path.join(CASA, "esteira.html"), "text/html; charset=utf-8")
        if p == "/api/quadro":
            return self._responder(cartoes_do_quadro(forcar="forcar" in q))
        if p == "/api/fluxos":
            comp = []
            try:
                import banco
                comp = banco.fluxos_listar()
            except Exception:
                pass
            return self._responder({"fluxos": listar_fluxos(), "compartilhados": comp,
                                    "panico": guarda.panico_ligado()})
        if p.startswith("/api/fluxo/"):
            try:
                return self._responder(json.load(open(caminho_fluxo(p[11:]), encoding="utf-8")))
            except FileNotFoundError:
                return self._responder({"erro": "esse fluxo não existe"}, 404)
        if p.startswith("/api/rodada/"):
            nome = p[12:]
            est = _rodando.get(nome)
            if not est:
                return self._responder({"rodando": False})
            return self._responder({"rodando": est["viva"], "passos": est["passos"],
                                    "modo": est["modo"], "diario": est.get("diario")})
        if p == "/api/modelos":
            import modelos as _m
            reg = _m.registro()
            return self._responder({"modelos": [
                {"id": k, **v} for k, v in reg.items()],
                "local_no_ar": _m._local_no_ar()})
        if p == "/api/term/lista":
            return self._responder({"terminais": terminais.lista()})
        if p.startswith("/api/term/saida/"):
            tid = p[16:]
            r = terminais.saida(tid, (q.get("desde") or ["0"])[0])
            if r is None:
                return self._responder({"erro": "terminal não existe"}, 404)
            return self._responder(r)
        if p == "/api/estado":
            return self._responder({"panico": guarda.panico_ligado(),
                                    "rodando": [k for k, v in _rodando.items() if v["viva"]],
                                    "casas": guarda.CASAS_PERMITIDAS,
                                    "teto_nos": guarda.MAX_NOS_POR_RODADA})
        self.send_error(404)

    # ────────────────────────────────────────────────────────────── POST
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        corpo = self._corpo_json()

        if p.startswith("/api/fluxo/"):
            nome = p[11:]
            fluxo = corpo or {}
            fluxo.setdefault("nome", os.path.basename(nome).replace(".json", ""))
            problemas = guarda.conferir_fluxo(fluxo)
            os.makedirs(FLUXOS, exist_ok=True)
            with open(caminho_fluxo(nome), "w", encoding="utf-8") as f:
                json.dump(fluxo, f, ensure_ascii=False, indent=1)
            # salvar sempre funciona — avisar dos problemas é outra coisa.
            # Impedir de salvar um rascunho meio pronto seria hostil.
            return self._responder({"salvo": True, "problemas": problemas,
                                    "ensaio": guarda.em_ensaio(fluxo)})

        if p.startswith("/api/rodar/"):
            nome = p[11:]
            valendo = bool(corpo.get("valendo"))
            try:
                fluxo = json.load(open(caminho_fluxo(nome), encoding="utf-8"))
            except FileNotFoundError:
                return self._responder({"erro": "esse fluxo não existe"}, 404)
            if _rodando.get(nome, {}).get("viva"):
                return self._responder({"erro": "esse fluxo já está rodando"}, 409)

            pode, modo, recados = guarda.liberado_pra_rodar(fluxo, forcar_ensaio=not valendo)
            if not pode:
                return self._responder({"rodou": False, "modo": modo, "recados": recados})

            est = {"viva": True, "passos": [], "modo": modo, "recados": recados}
            _rodando[nome] = est

            def trabalhar():
                try:
                    out = motor.rodar(fluxo, modo, ao_vivo=lambda r: est["passos"].append(r))
                    est["diario"] = out["diario"]
                except Exception as e:
                    est["passos"].append({"evento": "erro", "saida": str(e)})
                finally:
                    est["viva"] = False

            threading.Thread(target=trabalhar, daemon=True).start()
            return self._responder({"rodou": True, "modo": modo, "recados": recados})

        if p == "/api/liberar":
            nome = corpo.get("fluxo", "")
            try:
                fluxo = json.load(open(caminho_fluxo(nome), encoding="utf-8"))
            except FileNotFoundError:
                return self._responder({"erro": "esse fluxo não existe"}, 404)
            if corpo.get("soltar"):
                guarda.liberar(fluxo, corpo.get("por", "dono"))
            else:
                fluxo.pop("liberado", None)
            with open(caminho_fluxo(nome), "w", encoding="utf-8") as f:
                json.dump(fluxo, f, ensure_ascii=False, indent=1)
            return self._responder({"ensaio": guarda.em_ensaio(fluxo),
                                    "liberado": fluxo.get("liberado")})

        if p.startswith("/api/compartilhar/"):
            nome = p[18:].replace(".json", "")
            try:
                import banco
                fluxo = json.load(open(caminho_fluxo(nome), encoding="utf-8"))
                fluxo.pop("liberado", None)   # a liberação NUNCA viaja
                r = banco.fluxo_gravar(nome, fluxo)
                return self._responder({"ok": True, **r})
            except FileNotFoundError:
                return self._responder({"erro": "esse fluxo não existe aqui"}, 404)
            except Exception as e:
                return self._responder({"erro": str(e)}, 502)

        if p.startswith("/api/puxar/"):
            nome = p[11:].replace(".json", "")
            try:
                import banco
                corpo = banco.fluxo_abrir(nome)
                if not corpo:
                    return self._responder({"erro": "não existe no banco"}, 404)
                corpo.pop("liberado", None)   # chega preso: quem solta é você
                with open(caminho_fluxo(nome), "w", encoding="utf-8") as f:
                    json.dump(corpo, f, ensure_ascii=False, indent=1)
                return self._responder({"ok": True, "nome": nome})
            except Exception as e:
                return self._responder({"erro": str(e)}, 502)

        if p == "/api/term/criar":
            info = terminais.criar(corpo.get("nome") or "terminal",
                                   corpo.get("pasta") or "~",
                                   int(corpo.get("x") or 200), int(corpo.get("y") or 200))
            return self._responder(info)
        if p.startswith("/api/term/entrada/"):
            ok = terminais.entrada(p[18:], corpo.get("b64") or "")
            return self._responder({"ok": ok})
        if p.startswith("/api/term/tamanho/"):
            ok = terminais.tamanho(p[18:], corpo.get("cols") or 80, corpo.get("rows") or 24)
            return self._responder({"ok": ok})
        if p.startswith("/api/term/mover/"):
            ok = terminais.mover(p[16:], corpo.get("x") or 0, corpo.get("y") or 0,
                                 corpo.get("nome"))
            return self._responder({"ok": ok})
        if p.startswith("/api/term/fechar/"):
            ok = terminais.fechar(p[17:])
            return self._responder({"ok": ok})
        if p == "/api/panico":
            if corpo.get("puxar"):
                guarda.puxar_freio(corpo.get("motivo", "pedido pelo canvas"))
            else:
                guarda.soltar_freio()
            return self._responder({"panico": guarda.panico_ligado()})

        self.send_error(404)

    def log_message(self, *a):
        pass       # o terminal é do dono, não do servidor


def main():
    porta = PORTA_PADRAO
    if "--porta" in sys.argv:
        porta = int(sys.argv[sys.argv.index("--porta") + 1])
    # Threading é obrigatório com terminais vivos: cada card faz polling — num
    # servidor de fila única, um terminal penduraria todos os outros e a API.
    srv = ThreadingHTTPServer(("127.0.0.1", porta), Mao)   # só a própria máquina alcança
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║   A ESTEIRA                                                  ║
╚══════════════════════════════════════════════════════════════╝

   http://127.0.0.1:{porta}

   A chave do Trello fica AQUI, neste processo. O navegador
   recebe os cartões prontos e nunca vê credencial.

   Ctrl+C para desligar.
""")
    # o laço de gatilhos vive DENTRO do servidor: um processo só, o launchd
    # cuida dos dois. A cada 30 s: horário, quadro, webhooks — e derruba o
    # modelo local se ficou 10 min ocioso (12 GB não são aluguel grátis).
    threading.Thread(target=gatilhos.laco, args=(30,), daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ndesligado.")


if __name__ == "__main__":
    main()
