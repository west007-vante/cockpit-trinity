#!/usr/bin/env python3
"""O BANCO — o cliente das portas compartilhadas. Stdlib pura.

Tudo que os três sócios dividem passa por aqui: fluxos ("mesmas abas, mesmo
banco"), memória comum, recados entre máquinas e eventos de webhook. Nenhuma
tabela é tocada direto — só as funções-porta, com a credencial da máquina
(~/.steve/esteira.env, hash no banco, revogável no painel).

    python3 banco.py quem-sou
    python3 banco.py fluxo-enviar <nome>      # sobe um fluxo local pro banco
    python3 banco.py fluxo-puxar <nome>       # baixa um fluxo do banco
    python3 banco.py fluxos                   # lista o que os três compartilham
    python3 banco.py memoria "titulo" "corpo"
    python3 banco.py memoria                  # lê as últimas
"""
import json
import os
import sys
import urllib.request

ENV = os.path.expanduser("~/.steve/esteira.env")
CASA = os.path.dirname(os.path.abspath(__file__))


def _cfg():
    cfg = {}
    try:
        for ln in open(ENV, encoding="utf-8"):
            if "=" in ln and not ln.strip().startswith("#"):
                k, _, v = ln.partition("=")
                cfg[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return cfg


class BancoErro(Exception):
    pass


def porta(nome, **params):
    """Chama uma função-porta. Erro do banco vira mensagem legível."""
    cfg = _cfg()
    url, anon, cred = (cfg.get("ESTEIRA_SUPABASE_URL"),
                       cfg.get("ESTEIRA_SUPABASE_ANON"),
                       cfg.get("ESTEIRA_CREDENCIAL"))
    if not (url and anon and cred):
        raise BancoErro(f"sem credencial — {ENV} incompleto. "
                        "Gere no painel e cole lá (ESTEIRA_CREDENCIAL=...).")
    corpo = json.dumps({"p_credencial": cred, **params}).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/{nome}", data=corpo,
        headers={"apikey": anon, "Authorization": f"Bearer {anon}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            bruto = r.read().decode()
            return json.loads(bruto) if bruto.strip() else None
    except urllib.error.HTTPError as e:
        det = ""
        try:
            det = (json.loads(e.read().decode()).get("message") or "")[:200]
        except Exception:
            pass
        raise BancoErro(f"{nome} → {e.code}: {det}")


# atalhos com nome de gente
def quem_sou():                 return porta("esteira_quem_sou")
def fluxo_gravar(nome, corpo):  return porta("esteira_fluxo_gravar", p_nome=nome, p_corpo=corpo)
def fluxos_listar():            return porta("esteira_fluxos_listar")
def fluxo_abrir(nome):          return porta("esteira_fluxo_abrir", p_nome=nome)
def memoria_gravar(t, c):       return porta("esteira_memoria_gravar", p_titulo=t, p_corpo=c)
def memoria_ler(n=20):          return porta("esteira_memoria_ler", p_limite=n)
def recado_deixar(para, tipo, payload):
    return porta("esteira_recado_deixar", p_para=para, p_tipo=tipo, p_payload=payload)
def recados_puxar():            return porta("esteira_recados_puxar")
def recado_responder(rid, status, resultado):
    return porta("esteira_recado_responder", p_id=rid, p_status=status, p_resultado=resultado)
def recado_ver(rid):            return porta("esteira_recado_ver", p_id=rid)


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return
    try:
        if a[0] == "quem-sou":
            print(json.dumps(quem_sou(), ensure_ascii=False))
        elif a[0] == "fluxos":
            for f in fluxos_listar():
                print(f"  {f['nome']:24s} dono={f['dono']:6s} editado por {f['editado_por']} em {f['editado_em'][:16]}")
        elif a[0] == "fluxo-enviar" and len(a) > 1:
            nome = a[1].replace(".json", "")
            corpo = json.load(open(os.path.join(CASA, "fluxos", nome + ".json"), encoding="utf-8"))
            # a liberação NÃO viaja: solto aqui não é solto lá — quem libera é
            # o dono da máquina onde roda (princípio da plataforma)
            corpo.pop("liberado", None)
            print(json.dumps(fluxo_gravar(nome, corpo), ensure_ascii=False))
        elif a[0] == "fluxo-puxar" and len(a) > 1:
            nome = a[1].replace(".json", "")
            corpo = fluxo_abrir(nome)
            if not corpo:
                print(f"não existe '{nome}' no banco")
                return
            corpo.pop("liberado", None)      # chega preso: ensaio até o dono soltar
            destino = os.path.join(CASA, "fluxos", nome + ".json")
            json.dump(corpo, open(destino, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"✅ baixado pra {destino} (em ensaio — solte você se quiser)")
        elif a[0] == "memoria" and len(a) >= 3:
            print("id", memoria_gravar(a[1], a[2]))
        elif a[0] == "memoria":
            for m in memoria_ler(10):
                print(f"  [{m['autor']}] {m['titulo']} — {m['corpo'][:80]}")
        else:
            print(__doc__)
    except BancoErro as e:
        print(f"❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
