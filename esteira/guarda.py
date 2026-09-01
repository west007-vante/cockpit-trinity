#!/usr/bin/env python3
"""OS FREIOS — construídos ANTES do motor, de propósito.

A ESTEIRA dispara prompts de IA e comandos de terminal na máquina do dono, com
todo o acesso que ele tem. Um fluxo automático às 3 da manhã não tem ninguém pra
dizer "espera". Este arquivo é esse alguém.

Sete freios, cada um respondendo a uma forma diferente de dar errado:

  1. ENSAIO POR PADRÃO   fluxo novo não executa nada até o dono soltar
  2. GATE GRAVADO        soltar deixa data e hora no arquivo — dá pra auditar
  3. TETO DE RODADA      máximo de nós, timeout por nó, e CICLO barrado antes de começar
  4. PASTA DECLARADA     nó roda onde disse que roda, e em lugar nenhum além
  5. LISTA VERMELHA      apagar, publicar, mandar mensagem: gate humano SEMPRE
  6. DIÁRIO              nada roda sem deixar rastro
  7. PARAR-TUDO          um arquivo de pânico que qualquer rodada respeita

Funções puras onde dá: dá pra provar o freio inteiro sem executar nada.
"""
import json
import os
import re
import time

CASA = os.path.dirname(os.path.abspath(__file__))
PANICO = os.path.join(CASA, ".parar-tudo")

# ─────────────────────────────────────────────────────────── freio 3: tetos
MAX_NOS_POR_RODADA = 40        # fluxo maior que isso é desenho, não automação
TIMEOUT_PADRAO_S = 300         # 5 min por nó
TIMEOUT_MAX_S = 3600           # nem o dono pode pedir mais que 1h num nó só

# ─────────────────────────────────────────────── freio 4: onde é permitido rodar
# Um nó roda dentro de uma destas casas. Fora daqui, recusa — mesmo que o dono
# tenha escrito o caminho na mão, porque o erro de digitação é o caso comum.
CASAS_PERMITIDAS = [
    "~/mercador", "~/trinity", "~/quadro", "~/esteira", "~/steve", "~/maos",
    "~/Desktop", "~/Documents", "~/Pyerri-Vault", "~/Steve-Mac",
]

# ────────────────────────────────────────────────────── freio 5: lista vermelha
# Isto NÃO é uma lista de coisas proibidas. É a lista do que exige o dono na
# frente da tela — mesmo num fluxo que ele já soltou pra rodar sozinho.
VERMELHO = [
    (r"\brm\s+-[rf]{1,2}\b",        "apagar pasta inteira"),
    (r"\bsudo\b",                   "rodar como administrador"),
    (r"\bgit\s+push\b",             "publicar código"),
    (r"\bgit\s+reset\s+--hard\b",   "descartar trabalho não salvo"),
    (r"\bdrop\s+(table|schema|database)\b", "apagar dados do banco"),
    (r"\bdelete\s+from\b",          "apagar linhas do banco"),
    (r"\btruncate\b",               "esvaziar tabela"),
    # sem \b antes do hífen: "-X" começa com caractere que não é de palavra,
    # então a borda nunca casaria e o padrão passava batido.
    (r"\b(curl|wget|http)\b.*(-X\s*(POST|PUT|DELETE)|--data|-d\s)", "mandar dados pra fora"),
    (r"\bpublicar|\bpublish\b",     "publicar anúncio"),
    (r"\benviar|\bsend\b.*\b(email|whats|mensagem|message)", "mandar mensagem"),
    (r">\s*/dev/(sda|disk)",        "escrever em disco cru"),
    (r"\bmkfs\b|\bdiskutil\s+erase", "formatar"),
    (r"\bchmod\s+777\b",            "abrir permissão pra todo mundo"),
    (r"\b(shutdown|reboot|halt)\b", "desligar a máquina"),
]


class Barrado(Exception):
    """Um freio pegou. A mensagem diz qual e por quê — nunca só 'erro'."""


# ═══════════════════════════════════════════════════ freio 7: o botão de pânico
def panico_ligado():
    return os.path.exists(PANICO)


def puxar_freio(motivo="pedido pelo dono"):
    with open(PANICO, "w", encoding="utf-8") as f:
        f.write(json.dumps({"quando": time.strftime("%d/%m/%Y %H:%M:%S"),
                            "motivo": motivo}, ensure_ascii=False))
    return PANICO


def soltar_freio():
    try:
        os.remove(PANICO)
        return True
    except FileNotFoundError:
        return False


# ═══════════════════════════════════════════════ freio 1 e 2: ensaio e o gate
def _impressao(fluxo):
    """A impressão digital do CONTEÚDO executável (nós + fios, nada de posição).
    É o que amarra a liberação ao que foi de fato aprovado."""
    import hashlib
    nos = []
    for no in sorted((fluxo or {}).get("nos") or [], key=lambda x: x.get("id", "")):
        nos.append({k: v for k, v in no.items() if k not in ("x", "y", "titulo")})
    fios = sorted((fluxo or {}).get("fios") or [],
                  key=lambda f: (f.get("de", ""), f.get("para", ""), f.get("porta", "")))
    bruto = json.dumps({"nos": nos, "fios": fios}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode()).hexdigest()[:24]


def em_ensaio(fluxo):
    """Fluxo sem liberação explícita está em ensaio — e fluxo EDITADO depois de
    solto TAMBÉM: a liberação vale pro conteúdo aprovado, não pro nome do arquivo.
    Trocou um comando, uma URL, um fio? Volta pro ensaio até alguém re-aprovar.
    (Mexer só na posição dos nós ou no título não conta — isso é estética.)"""
    lib = (fluxo or {}).get("liberado")
    if not (isinstance(lib, dict) and lib.get("por") and lib.get("quando")):
        return True
    return lib.get("impressao") != _impressao(fluxo)


def liberar(fluxo, por="dono"):
    """Sair do ensaio deixa rastro E amarra a impressão digital do conteúdo."""
    fluxo["liberado"] = {"por": por, "quando": time.strftime("%d/%m/%Y %H:%M:%S"),
                         "impressao": _impressao(fluxo)}
    return fluxo


# ══════════════════════════════════════════════════ freio 3: ciclo e tamanho
def achar_ciclo(nos, fios):
    """Devolve o caminho do ciclo, ou None. Roda ANTES de executar qualquer coisa —
    um fluxo que se morde não pode nem começar."""
    saida = {}
    for f in fios:
        saida.setdefault(f["de"], []).append(f["para"])
    BRANCO, CINZA, PRETO = 0, 1, 2
    cor = {n["id"]: BRANCO for n in nos}
    caminho = []

    def anda(u):
        cor[u] = CINZA
        caminho.append(u)
        for v in saida.get(u, []):
            if cor.get(v) == CINZA:
                return caminho[caminho.index(v):] + [v]
            if cor.get(v) == BRANCO:
                r = anda(v)
                if r:
                    return r
        cor[u] = PRETO
        caminho.pop()
        return None

    for n in nos:
        if cor[n["id"]] == BRANCO:
            r = anda(n["id"])
            if r:
                return r
    return None


def conferir_fluxo(fluxo):
    """Tudo que dá pra saber SEM executar. Devolve a lista de problemas."""
    problemas = []
    nos = fluxo.get("nos") or []
    fios = fluxo.get("fios") or []

    if not nos:
        problemas.append("o fluxo está vazio")
    if len(nos) > MAX_NOS_POR_RODADA:
        problemas.append(f"{len(nos)} nós — o teto é {MAX_NOS_POR_RODADA}. "
                         "Fluxo maior que isso é desenho, não automação.")

    ids = {n["id"] for n in nos}
    for f in fios:
        if f.get("de") not in ids:
            problemas.append(f"fio saindo de um nó que não existe: {f.get('de')}")
        if f.get("para") not in ids:
            problemas.append(f"fio chegando num nó que não existe: {f.get('para')}")

    ciclo = achar_ciclo(nos, [f for f in fios if f.get("de") in ids and f.get("para") in ids])
    if ciclo:
        problemas.append("o fluxo se morde: " + " → ".join(ciclo) +
                         ". Ia rodar pra sempre — por isso nem começa.")

    for n in nos:
        problemas += conferir_no(n)
    return problemas


def conferir_no(no):
    """Os freios 4 e 5, num nó só."""
    out = []
    tipo = no.get("tipo")
    nome = no.get("titulo") or no.get("id")

    if tipo in ("agente", "comando"):
        pasta = no.get("pasta")
        if not pasta:
            out.append(f'"{nome}": nó de {tipo} sem pasta declarada — '
                       "diga em que pasta ele roda.")
        else:
            ok, motivo = pasta_permitida(pasta)
            if not ok:
                out.append(f'"{nome}": {motivo}')

    if tipo == "comando":
        cmd = no.get("comando") or ""
        if not cmd.strip():
            out.append(f'"{nome}": nó de comando sem comando.')
        for achado, oque in vermelho(cmd):
            out.append(f'🔴 "{nome}": {oque} — "{achado}". '
                       "Isso passa por você mesmo em fluxo solto.")

    if tipo == "webhook":
        url = (no.get("url") or "").strip()
        if not url:
            out.append(f'"{nome}": nó de webhook sem URL.')
        elif not url.startswith("https://"):
            out.append(f'🔴 "{nome}": webhook pra {url[:40]} — só HTTPS. '
                       "http:// manda seu dado aberto pela rede.")
        corpo = no.get("corpo")
        if corpo is not None and not isinstance(corpo, (dict, list)):
            out.append(f'"{nome}": o corpo do webhook precisa ser JSON (objeto ou lista).')

    if tipo == "terminal":
        acao = no.get("acao") or "criar"
        if acao not in ("criar", "digitar", "esperar", "ler", "fechar"):
            out.append(f'"{nome}": ação de terminal desconhecida: {acao}')
        if not (no.get("nome") or "").strip():
            out.append(f'"{nome}": diga o NOME do terminal (é como o fluxo o encontra).')
        if acao in ("digitar", "esperar") and not (no.get("texto") or "").strip():
            out.append(f'"{nome}": a ação {acao} precisa do TEXTO.')
        if acao == "digitar" and no.get("enter", True):
            # digitar COM Enter é executar — a lista vermelha vale inteira.
            # SEM Enter (enter=false) é rascunho: o texto fica parado no prompt
            # e o Enter é do DONO, no terminal do canvas — o gate físico literal.
            for achado, oque in vermelho(no.get("texto") or ""):
                out.append(f'🔴 "{nome}": digitaria {oque} — "{achado}". Passa por você.')

    if tipo == "app":
        if not (no.get("app") or "").strip():
            out.append(f'"{nome}": nó de app sem o aplicativo alvo.')
        if not (no.get("pedido") or "").strip():
            out.append(f'"{nome}": nó de app sem a tarefa.')
        for achado, oque in vermelho(no.get("pedido") or ""):
            out.append(f'🔴 "{nome}": a tarefa no app manda {oque} — "{achado}". Passa por você.')

    if tipo == "agente":
        if not (no.get("pedido") or "").strip():
            out.append(f'"{nome}": nó de agente sem pedido escrito.')
        for achado, oque in vermelho(no.get("pedido") or ""):
            out.append(f'🔴 "{nome}": o pedido manda {oque} — "{achado}". '
                       "Passa por você.")

    t = no.get("timeout_s")
    if t is not None and (not isinstance(t, int) or t < 1 or t > TIMEOUT_MAX_S):
        out.append(f'"{nome}": timeout de {t}s fora do permitido (1–{TIMEOUT_MAX_S}).')
    return out


# ═══════════════════════════════════════════════════════ freio 4: a pasta
def pasta_permitida(pasta):
    """Resolve o caminho de verdade (symlink e .. incluídos) antes de julgar —
    senão "~/Desktop/../../../etc" passaria."""
    try:
        real = os.path.realpath(os.path.expanduser(pasta))
    except Exception:
        return False, f"caminho inválido: {pasta}"
    if not os.path.isdir(real):
        return False, f"a pasta não existe: {pasta}"
    for casa in CASAS_PERMITIDAS:
        raiz = os.path.realpath(os.path.expanduser(casa))
        if real == raiz or real.startswith(raiz + os.sep):
            return True, ""
    return False, (f"a pasta {pasta} está fora das casas permitidas. "
                   "Se ela devia estar, acrescente em CASAS_PERMITIDAS no guarda.py.")


# ══════════════════════════════════════════════════ freio 5: a lista vermelha
def vermelho(texto):
    """Todos os motivos pelos quais este texto precisa do dono na frente."""
    t = (texto or "").lower()
    return [(m.group(0), oque) for padrao, oque in VERMELHO
            for m in [re.search(padrao, t, re.I)] if m]


def precisa_do_dono(no):
    tipo = no.get("tipo")
    alvo = no.get("comando") if tipo == "comando" else no.get("pedido") if tipo == "agente" else ""
    return vermelho(alvo)


# ══════════════════════════════════════════════════════ o porteiro da rodada
def liberado_pra_rodar(fluxo, forcar_ensaio=False):
    """A decisão final, num lugar só. Devolve (pode_executar, modo, recados)."""
    recados = []
    if panico_ligado():
        try:
            d = json.load(open(PANICO, encoding="utf-8"))
            recados.append(f"🛑 O freio de pânico está puxado desde {d.get('quando')} "
                           f"({d.get('motivo')}). Solte com: ./daemon.sh soltar-freio")
        except Exception:
            recados.append("🛑 O freio de pânico está puxado.")
        return False, "parado", recados

    problemas = conferir_fluxo(fluxo)
    graves = [p for p in problemas if not p.startswith("🔴")]
    if graves:
        return False, "parado", ["❌ " + p for p in graves]

    if forcar_ensaio or em_ensaio(fluxo):
        porque = ("você pediu ensaio" if forcar_ensaio
                  else "este fluxo nunca foi solto — todo fluxo nasce em ensaio")
        recados.append(f"🎭 ENSAIO ({porque}). Mostro o que faria; não faço nada.")
        return True, "ensaio", recados + ["⚠️ " + p for p in problemas if p.startswith("🔴")]

    lib = fluxo["liberado"]
    recados.append(f"▶️ VALENDO — solto por {lib['por']} em {lib['quando']}.")
    for p in problemas:
        if p.startswith("🔴"):
            recados.append("⚠️ " + p + " (vai parar e te perguntar)")
    return True, "valendo", recados


if __name__ == "__main__":
    print("═══ PROVA DOS FREIOS — nada é executado ═══\n")
    ok = falhou = 0

    def prova(desc, condicao):
        global ok, falhou
        if condicao:
            ok += 1
            print(f"  ✅ {desc}")
        else:
            falhou += 1
            print(f"  ❌ {desc}")

    print("── freio 1: ensaio por padrão ──")
    prova("fluxo novo nasce em ensaio", em_ensaio({"nos": []}))
    prova("campo 'liberado' mentiroso não engana", em_ensaio({"liberado": {"por": "x"}}))
    prova("liberado de verdade sai do ensaio", not em_ensaio(liberar({}, "dono")))

    print("\n── freio 3: ciclo barrado antes de rodar ──")
    nos = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    prova("A→B→C não tem ciclo",
          achar_ciclo(nos, [{"de": "a", "para": "b"}, {"de": "b", "para": "c"}]) is None)
    c = achar_ciclo(nos, [{"de": "a", "para": "b"}, {"de": "b", "para": "c"}, {"de": "c", "para": "a"}])
    prova(f"A→B→C→A é pego: {' → '.join(c or [])}", c is not None)
    prova("nó que aponta pra si mesmo é pego",
          achar_ciclo([{"id": "a"}], [{"de": "a", "para": "a"}]) is not None)

    print("\n── freio 4: a pasta ──")
    prova("~/esteira é permitida", pasta_permitida("~/esteira")[0])
    prova("/etc é recusada", not pasta_permitida("/etc")[0])
    prova("escapar com .. não funciona", not pasta_permitida("~/Desktop/../../../etc")[0])
    prova("pasta que não existe é recusada", not pasta_permitida("~/nao-existe-mesmo")[0])

    print("\n── freio 5: a lista vermelha ──")
    for cmd, esperado in [("rm -rf ~/mercador", True), ("sudo apt install", True),
                          ("git push origin main", True), ("python3 build.py", False),
                          ("ls -la", False), ("DELETE FROM leads", True),
                          ("curl -X POST https://x.com --data @a", True)]:
        achados = vermelho(cmd)
        prova(f"{'pega' if esperado else 'deixa passar'}: {cmd[:34]}", bool(achados) == esperado)

    print("\n── o porteiro ──")
    bom = {"nos": [{"id": "a", "tipo": "comando", "titulo": "listar",
                    "pasta": "~/esteira", "comando": "ls -la"}], "fios": []}
    pode, modo, _ = liberado_pra_rodar(bom)
    prova("fluxo bom, sem liberação → roda em ENSAIO", pode and modo == "ensaio")
    pode, modo, _ = liberado_pra_rodar(liberar(dict(bom), "dono"))
    prova("fluxo bom, liberado → VALENDO", pode and modo == "valendo")

    ruim = {"nos": [{"id": "a", "tipo": "comando", "titulo": "x",
                     "pasta": "/etc", "comando": "ls"}], "fios": []}
    pode, modo, rec = liberado_pra_rodar(liberar(ruim, "dono"))
    prova("pasta proibida barra mesmo liberado", not pode)

    print("\n── freio 7: o pânico ──")
    puxar_freio("prova automática")
    pode, modo, _ = liberado_pra_rodar(liberar(dict(bom), "dono"))
    prova("com o freio puxado, nem fluxo liberado roda", not pode and modo == "parado")
    soltar_freio()
    prova("soltando o freio, volta a rodar", liberado_pra_rodar(liberar(dict(bom), "dono"))[0])

    print(f"\n{'═' * 52}\n  {ok} provas passaram, {falhou} falharam")
    raise SystemExit(1 if falhou else 0)
