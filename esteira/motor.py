#!/usr/bin/env python3
"""O MOTOR — executa o fluxo. Passa pelo guarda antes de cada nó, sempre.

Ordem: os nós sem entrada começam; cada nó espera todos os pais terminarem.
A condição escolhe por qual fio seguir; o dividir segue todos.

Dois modos, e a diferença é absoluta:
  🎭 ENSAIO   descreve o que faria. NÃO abre processo, NÃO toca no Trello.
  ▶️ VALENDO  executa. Só entra aqui fluxo que o dono soltou explicitamente.

Todo nó, nos dois modos, deixa linha no diário. Nada roda sem rastro.

    python3 motor.py fluxos/meu.json              # ensaio (o padrão)
    python3 motor.py fluxos/meu.json --valendo    # executa, se o fluxo foi solto
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guarda    # noqa: E402
import modelos   # noqa: E402
import contexto  # noqa: E402
import memoria   # noqa: E402

CASA = os.path.dirname(os.path.abspath(__file__))
DIARIO_DIR = os.path.join(CASA, "execucoes")


class Diario:
    """Uma linha por acontecimento. É o que responde 'o que essa coisa fez?'."""

    def __init__(self, fluxo_nome, modo):
        os.makedirs(DIARIO_DIR, exist_ok=True)
        self.id = f"{time.strftime('%Y%m%d-%H%M%S')}-{fluxo_nome}"
        self.caminho = os.path.join(DIARIO_DIR, self.id + ".jsonl")
        self.linhas = []
        self.escrever("rodada", fluxo=fluxo_nome, modo=modo,
                      quando=time.strftime("%d/%m/%Y %H:%M:%S"))

    def escrever(self, evento, **campos):
        # "evento" é o que aconteceu (começou/terminou/pulou); "tipo" é o tipo do
        # nó. Nomes separados de propósito: um registro carrega os dois.
        reg = {"t": round(time.time(), 3), "evento": evento, **campos}
        self.linhas.append(reg)
        try:
            with open(self.caminho, "a", encoding="utf-8") as f:
                f.write(json.dumps(reg, ensure_ascii=False) + "\n")
        except Exception:
            pass
        return reg


def _dono_local():
    try:
        for ln in open(os.path.expanduser("~/.steve/esteira.env"), encoding="utf-8"):
            if ln.startswith("ESTEIRA_DONO="):
                return ln.split("=", 1)[1].strip().lower()
    except Exception:
        pass
    return "steve"


def carregar(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _entradas(nos, fios):
    """Quantos pais cada nó tem — quem tem zero começa."""
    conta = {n["id"]: 0 for n in nos}
    for f in fios:
        if f["para"] in conta:
            conta[f["para"]] += 1
    return conta


# ═══════════════════════════════════════════════════════ os seis tipos de nó
def faz_comando(no, modo, diario):
    cmd = no.get("comando", "")
    pasta = os.path.expanduser(no.get("pasta", "~"))
    limite = min(no.get("timeout_s") or guarda.TIMEOUT_PADRAO_S, guarda.TIMEOUT_MAX_S)
    if modo == "ensaio":
        return {"ok": True, "saida": f"[ensaio] rodaria em {pasta}:\n  $ {cmd}", "ensaio": True}
    try:
        r = subprocess.run(cmd, shell=True, cwd=pasta, capture_output=True,
                           text=True, timeout=limite)
        saida = (r.stdout or "") + (("\n[erro]\n" + r.stderr) if r.stderr else "")
        return {"ok": r.returncode == 0, "codigo": r.returncode, "saida": saida[:8000]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "saida": f"estourou o tempo ({limite}s) e foi morto."}
    except Exception as e:
        return {"ok": False, "saida": f"não consegui rodar: {e}"}


def faz_remoto(no, modo, fluxo_nome, saida_anterior):
    """O nó com executor de OUTRO sócio: vira recado na fila compartilhada.
    O daemon da máquina dele puxa, roda com os freios DELE, devolve o resultado.
    Aqui a gente só espera — com paciência declarada e fim honesto."""
    import banco
    para = no.get("executor")
    espera_max = min(no.get("timeout_s") or 600, 1800)
    if modo == "ensaio":
        return {"ok": True, "ensaio": True,
                "saida": f"[ensaio] deixaria o nó '{no.get('titulo')}' na fila pra "
                         f"{para.upper()} executar na máquina dele (espera de até {espera_max}s)"}
    carga = {"no": {k: v for k, v in no.items() if k not in ("x", "y", "executor")},
             "fluxo_nome": fluxo_nome, "saida_anterior": (saida_anterior or "")[:4000]}
    try:
        rid = banco.recado_deixar(para, "no", carga)
    except Exception as e:
        return {"ok": False, "saida": f"não consegui deixar o recado: {e}"}
    t0 = time.time()
    while time.time() - t0 < espera_max:
        if guarda.panico_ligado():
            return {"ok": False, "saida": f"freio puxado enquanto esperava o recado #{rid}"}
        time.sleep(6)
        try:
            v = banco.recado_ver(rid) or {}
        except Exception:
            continue
        if v.get("status") in ("feito", "erro", "recusado"):
            r = v.get("resultado") or {}
            return {"ok": v["status"] == "feito" and r.get("ok", True),
                    "saida": f"[{para} · {v['status']}] " + str(r.get("saida", ""))[:6000],
                    "remoto": True, "recado": rid}
    return {"ok": False, "saida": f"o recado #{rid} pra {para} não voltou em {espera_max}s "
            "(a máquina dele está ligada? o daemon roda?)"}


def faz_agente(no, modo, diario, saida_anterior, pasta_execucao=None):
    """O nó Agente v2 — a construção que o dono pediu, igual ao n8n:
    QUAL MODELO pensa (claude nuvem / gpt-oss local / FLUX imagem, via modelos.py),
    QUAL CONTEXTO ele recebe (pastas, cofres Obsidian, cards — via contexto.py),
    QUAL MEMÓRIA ele carrega antes e grava depois (comum/tarefa/isolada)."""
    pedido = no.get("pedido", "")
    modelo = no.get("modelo") or "claude"
    pasta = no.get("pasta", "~")
    limite = min(no.get("timeout_s") or 900, guarda.TIMEOUT_MAX_S)

    # 1. a memória entra ANTES — o agente lembra do que já viveu
    mem = no.get("memoria") if (no.get("memoria") or {}).get("tipo") else None
    lembranca = memoria.carregar(mem, pasta_execucao) if mem else ""

    # 2. o pacote de contexto
    fontes = no.get("contexto") or []
    pacote = contexto.montar(fontes, pedido) if fontes else ""

    # 3. o prompt final, por camadas — pedido primeiro, apoio depois
    partes = [pedido]
    if pacote:
        partes.append("═══ CONTEXTO ═══\n" + pacote)
    if lembranca:
        partes.append("═══ O QUE VOCÊ LEMBRA ═══\n" + lembranca)
    if saida_anterior and no.get("usar_saida_anterior", True):
        partes.append("═══ DO PASSO ANTERIOR ═══\n" + saida_anterior[:4000])
    prompt = "\n\n".join(partes)

    if modo == "ensaio":
        detalhe = (f"[ensaio] modelo={modelo} · pasta={pasta}"
                   f" · contexto={len(pacote)} chars ({len(fontes)} fonte(s))"
                   f" · memória={'%s (%d chars)' % (mem.get('tipo'), len(lembranca)) if mem else 'nenhuma'}"
                   f"\n  pedido: {pedido[:400]}{'…' if len(pedido) > 400 else ''}")
        return {"ok": True, "ensaio": True, "saida": detalhe}

    # O agente headless precisa poder ESCREVER na pasta em que trabalha —
    # sem isso o fichador da Luciene gravou no limbo. acceptEdits libera
    # Write/Edit no diretório de trabalho; Bash perigoso continua pedindo dono.
    extras = ["--permission-mode", "acceptEdits"] if modelo == "claude" else None
    r = modelos.chamar(modelo, prompt, pasta=pasta, timeout_s=limite, args_extras=extras)
    r.setdefault("saida", "")

    # 4. a memória grava DEPOIS — só rodada de verdade que deu certo vira lembrança
    if mem and r.get("ok"):
        memoria.gravar(mem, no.get("titulo") or no.get("id", "nó"),
                       (r.get("saida") or "")[:1200], pasta_execucao)
    return r


def faz_tarefa(no, modo, diario, fluxo_nome=""):
    """Mexe num cartão do quadro: move de lista, comenta, marca feito."""
    card = no.get("card_id")
    destino = no.get("mover_para")
    recado = no.get("comentar")
    if not card:
        return {"ok": False, "saida": "nó de tarefa sem cartão escolhido."}
    if modo == "ensaio":
        o = []
        if destino:
            o.append(f"moveria o cartão pra {destino}")
        if recado:
            o.append(f'comentaria: "{recado[:80]}"')
        return {"ok": True, "ensaio": True, "saida": "[ensaio] " + (" e ".join(o) or "não faria nada")}
    try:
        sys.path.insert(0, os.path.expanduser("~/trinity/trello"))
        # o quadro mostra QUAL fluxo mexeu, não um "Steve" genérico
        os.environ.setdefault("TRELLO_ASSINATURA", f"esteira·{fluxo_nome or 'fluxo'}")
        from trello_api import Trello
        from comum import Indice
        t = Trello()
        feito = []
        if destino:
            idx = Indice(t)
            t.mover_card(card, idx.lista(destino))
            feito.append(f"movido pra {destino}")
        if recado:
            t.comentar(card, recado)
            feito.append("comentado")
        return {"ok": True, "saida": "cartão " + ", ".join(feito) if feito else "nada a fazer"}
    except Exception as e:
        return {"ok": False, "saida": f"o Trello recusou: {e}"}


def faz_condicao(no, contexto_ok, contexto_saida, modo):
    """Decide por qual porta sair. Não executa nada — só escolhe o caminho."""
    regra = no.get("regra", "deu_certo")
    if regra == "deu_certo":
        passou = bool(contexto_ok)
        porque = "o passo anterior deu certo" if passou else "o passo anterior falhou"
    elif regra == "falhou":
        passou = not contexto_ok
        porque = "o passo anterior falhou" if passou else "o passo anterior deu certo"
    elif regra == "contem":
        alvo = no.get("texto", "")
        passou = alvo.lower() in (contexto_saida or "").lower()
        porque = f'a saída {"contém" if passou else "não contém"} "{alvo}"'
    else:
        return {"ok": False, "saida": f"regra desconhecida: {regra}"}
    return {"ok": True, "porta": "sim" if passou else "nao",
            "saida": f"{'✅ SIM' if passou else '❌ NÃO'} — {porque}"}


def faz_webhook(no, modo, saida_anterior=""):
    """Enviar webhook — o canal SANCIONADO de falar com o mundo lá fora.
    (curl POST solto em nó de comando continua caindo na lista vermelha;
    aqui a URL é declarada, conferida pelo guarda e registrada no diário.)"""
    import urllib.request
    url = (no.get("url") or "").strip()
    corpo = no.get("corpo")
    if corpo is None:
        corpo = {}
    if isinstance(corpo, dict) and no.get("juntar_saida", True) and saida_anterior:
        corpo = {**corpo, "saida_anterior": saida_anterior[:4000]}
    if modo == "ensaio":
        return {"ok": True, "ensaio": True,
                "saida": f"[ensaio] mandaria POST pra {url}\n  corpo: {json.dumps(corpo, ensure_ascii=False)[:300]}"}
    try:
        req = urllib.request.Request(
            url, data=json.dumps(corpo, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=min(no.get("timeout_s") or 30, 120)) as r:
            resp = r.read().decode()[:2000]
            return {"ok": 200 <= r.status < 300, "codigo": r.status,
                    "saida": f"HTTP {r.status} · {resp[:800]}"}
    except Exception as e:
        return {"ok": False, "saida": f"o destino não aceitou: {e}"}


def _term_achar(nome):
    import terminais
    for t in terminais.lista():
        if t["nome"] == nome and t["vivo"]:
            return t
    return None


def _sem_ansi(texto):
    """Saída de terminal vem suja de códigos de cor/cursor. Pra virar contexto
    de agente ou condição, entra limpa."""
    import re
    texto = re.sub(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)", "", texto)
    texto = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", texto)
    return texto.replace("\r", "")


def faz_terminal(no, modo):
    """Nó 🖥️ — o FLUXO operando os terminais VIVOS do canvas. O que você faz
    com as mãos (criar, digitar, ler), a automação faz sozinha — e você VÊ:
    o terminal nasce e trabalha na sua frente, no canvas.

      criar    abre um shell real no canvas (idempotente: nome já vivo = reusa)
      digitar  manda texto pro shell (com Enter, a não ser que enter=false)
      esperar  segura o fluxo até um texto aparecer na saída (ou estourar)
      ler      devolve as últimas linhas (vira contexto pro próximo nó)
      fechar   encerra o shell
    """
    import base64
    import terminais
    acao = no.get("acao") or "criar"
    nome = (no.get("nome") or "").strip()

    if modo == "ensaio":
        desc = {"criar": f"abriria o terminal {nome!r} em {no.get('pasta') or '~'}",
                "digitar": f"digitaria em {nome!r}: {(no.get('texto') or '')[:120]!r}",
                "esperar": f"esperaria {nome!r} mostrar {(no.get('texto') or '')[:80]!r}",
                "ler": f"leria as últimas {no.get('linhas') or 30} linhas de {nome!r}",
                "fechar": f"fecharia o terminal {nome!r}"}.get(acao, acao)
        return {"ok": True, "ensaio": True, "saida": f"[ensaio] {desc}"}

    if acao == "criar":
        ja = _term_achar(nome)
        if ja:
            return {"ok": True, "saida": f"o terminal {nome!r} já está vivo — reusando (id {ja['id']})"}
        n_vivos = len([t for t in terminais.lista() if t["vivo"]])
        info = terminais.criar(nome or "terminal", no.get("pasta") or "~",
                               240 + (n_vivos % 3) * 600, 140 + (n_vivos // 3) * 380)
        time.sleep(1.0)          # o zsh sobe e pinta o prompt
        return {"ok": True, "saida": f"terminal {nome!r} aberto no canvas (id {info['id']})"}

    t = _term_achar(nome)
    if not t:
        vivos = ", ".join(x["nome"] for x in terminais.lista() if x["vivo"]) or "nenhum"
        return {"ok": False, "saida": f"não achei o terminal {nome!r} vivo. Vivos: {vivos}"}

    if acao == "digitar":
        texto = no.get("texto") or ""
        if no.get("enter", True):
            texto += "\n"
        ok = terminais.entrada(t["id"], base64.b64encode(texto.encode()).decode())
        return {"ok": ok, "saida": f"digitado em {nome!r}: {texto.strip()[:200]!r}"}

    if acao == "esperar":
        alvo = no.get("texto") or ""
        limite = min(no.get("timeout_s") or 120, guarda.TIMEOUT_MAX_S)
        marco = terminais.saida(t["id"], 0)["desde"]     # só o que vier DAQUI em diante
        acumulado = ""
        t0 = time.time()
        while time.time() - t0 < limite:
            if guarda.panico_ligado():
                return {"ok": False, "saida": "freio de pânico puxado durante a espera"}
            time.sleep(0.5)
            r = terminais.saida(t["id"], marco)
            if r is None:
                return {"ok": False, "saida": f"o terminal {nome!r} fechou no meio da espera"}
            marco = r["desde"]
            acumulado += _sem_ansi(base64.b64decode(r["dados"]).decode("utf-8", "replace"))
            if alvo and alvo in acumulado:
                return {"ok": True, "saida": f"apareceu {alvo!r} depois de {round(time.time()-t0,1)}s"}
            if not r["vivo"]:
                return {"ok": False, "saida": f"o shell de {nome!r} terminou sem mostrar {alvo!r}"}
        return {"ok": False, "saida": f"{alvo!r} não apareceu em {limite}s"}

    if acao == "ler":
        r = terminais.saida(t["id"], 0)
        limpo = _sem_ansi(base64.b64decode(r["dados"]).decode("utf-8", "replace"))
        linhas = [l for l in limpo.splitlines() if l.strip()]
        n = int(no.get("linhas") or 30)
        return {"ok": True, "saida": "\n".join(linhas[-n:]) or "(vazio)"}

    if acao == "fechar":
        terminais.fechar(t["id"])
        return {"ok": True, "saida": f"terminal {nome!r} fechado"}

    return {"ok": False, "saida": f"ação desconhecida: {acao}"}


def faz_app(no, modo, saida_anterior=""):
    """Nó 🖐 App — o agente com olhos e mãos no aplicativo REAL, via ~/maos.
    Por baixo é um agente claude com a instrução de seguir o PROTOCOLO."""
    app = no.get("app") or ""
    pedido = no.get("pedido") or ""
    prompt = (
        "Você vai operar um aplicativo nativo do macOS usando o protocolo MÃOS.\n"
        "1. Leia ~/maos/PROTOCOLO.md e rode `~/maos/maos doutor --json` PRIMEIRO.\n"
        "2. Se houver permissão faltando, PARE e reporte — não contorne.\n"
        f"3. O aplicativo alvo: {app}\n"
        f"4. A tarefa: {pedido}\n"
        "5. Ao final, reporte o que fez e o que viu, em 5 linhas.\n"
        + (f"\nContexto do passo anterior:\n{saida_anterior[:2000]}" if saida_anterior else ""))
    if modo == "ensaio":
        return {"ok": True, "ensaio": True,
                "saida": f"[ensaio] chamaria o agente-com-mãos no app {app!r}: {pedido[:200]}"}
    import modelos
    # Permissão CIRÚRGICA: o processo deste nó pré-aprova APENAS o binário das
    # mãos. Nenhum outro comando ganha carona — e a lista vermelha da esteira
    # já barrou pedido perigoso antes de chegar aqui.
    maos_bin = os.path.expanduser("~/maos/maos")
    return modelos.chamar("claude", prompt, pasta="~/maos",
                          timeout_s=min(no.get("timeout_s") or 600, guarda.TIMEOUT_MAX_S),
                          args_extras=["--allowedTools", f"Bash({maos_bin}:*)"])


def faz_espera(no, modo):
    mins = no.get("minutos", 1)
    if modo == "ensaio":
        return {"ok": True, "ensaio": True, "saida": f"[ensaio] esperaria {mins} min"}
    fim = time.time() + mins * 60
    while time.time() < fim:
        if guarda.panico_ligado():
            return {"ok": False, "saida": "o freio de pânico foi puxado durante a espera."}
        time.sleep(min(5, max(0, fim - time.time())))
    return {"ok": True, "saida": f"esperou {mins} min"}


# ══════════════════════════════════════════════════════════════ a rodada
def rodar(fluxo, modo="ensaio", diario=None, ao_vivo=None):
    """Executa o fluxo inteiro. `ao_vivo(reg)` é chamado a cada passo, pro editor
    poder acender o nó na tela enquanto roda."""
    nos = {n["id"]: n for n in fluxo.get("nos", [])}
    fios = fluxo.get("fios", [])
    diario = diario or Diario(fluxo.get("nome", "sem-nome"), modo)

    def conta(reg):
        if ao_vivo:
            try:
                ao_vivo(reg)
            except Exception:
                pass
        return reg

    faltam = _entradas(fluxo.get("nos", []), fios)
    prontos = [i for i, n in faltam.items() if n == 0]
    resultado = {}
    feitos = 0
    saida_de = {}

    while prontos:
        if guarda.panico_ligado():
            conta(diario.escrever("parado", motivo="freio de pânico puxado no meio da rodada"))
            break
        if feitos >= guarda.MAX_NOS_POR_RODADA:
            conta(diario.escrever("parado", motivo=f"teto de {guarda.MAX_NOS_POR_RODADA} nós"))
            break

        nid = prontos.pop(0)
        no = nos[nid]
        tipo = no.get("tipo")
        titulo = no.get("titulo") or nid

        # o freio 5 vale AQUI também: em fluxo solto, o vermelho para e pergunta
        if modo == "valendo":
            perigos = guarda.precisa_do_dono(no)
            if perigos:
                conta(diario.escrever("gate", no=nid, titulo=titulo,
                                      motivos=[o for _, o in perigos],
                                      saida="🔴 parei: isto precisa de você na frente da tela."))
                resultado[nid] = {"ok": False, "saida": "parado pelo gate humano", "gate": True}
                feitos += 1
                continue

        conta(diario.escrever("começou", no=nid, titulo=titulo, tipo=tipo))
        t0 = time.time()

        pais = [f["de"] for f in fios if f["para"] == nid]
        ctx_saida = "\n".join(saida_de.get(p, "") for p in pais).strip()
        ctx_ok = all(resultado.get(p, {}).get("ok", True) for p in pais)

        if tipo == "comando":
            r = faz_comando(no, modo, diario)
        elif tipo == "agente":
            executor = (no.get("executor") or "").strip().lower()
            meu = _dono_local()
            if executor and executor not in ("", "local", meu):
                r = faz_remoto(no, modo, fluxo.get("nome", ""), ctx_saida)
            else:
                r = faz_agente(no, modo, diario, ctx_saida,
                               pasta_execucao=os.path.join(DIARIO_DIR, diario.id + ".mem"))
        elif tipo == "tarefa":
            r = faz_tarefa(no, modo, diario, fluxo.get("nome", ""))
        elif tipo == "condicao":
            r = faz_condicao(no, ctx_ok, ctx_saida, modo)
        elif tipo == "terminal":
            r = faz_terminal(no, modo)
        elif tipo == "app":
            r = faz_app(no, modo, ctx_saida)
        elif tipo == "webhook":
            r = faz_webhook(no, modo, ctx_saida)
        elif tipo == "espera":
            r = faz_espera(no, modo)
        elif tipo == "dividir":
            r = {"ok": True, "saida": "soltou todos os caminhos"}
        else:
            r = {"ok": False, "saida": f"não sei executar um nó do tipo '{tipo}'"}

        r["duracao_s"] = round(time.time() - t0, 2)
        resultado[nid] = r
        saida_de[nid] = r.get("saida", "")
        feitos += 1
        conta(diario.escrever("terminou", no=nid, titulo=titulo, tipo=tipo,
                              ok=r.get("ok"), duracao_s=r["duracao_s"],
                              saida=(r.get("saida") or "")[:2000]))

        # solta os filhos — a condição solta só a porta que escolheu
        for f in fios:
            if f["de"] != nid:
                continue
            if tipo == "condicao" and f.get("porta") and f["porta"] != r.get("porta"):
                conta(diario.escrever("pulou", no=f["para"],
                                      motivo=f"a condição foi pela porta {r.get('porta')}"))
                faltam[f["para"]] = max(0, faltam[f["para"]] - 1)
                continue
            faltam[f["para"]] -= 1
            if faltam[f["para"]] == 0:
                prontos.append(f["para"])

    # a memória "tarefa" morre com a rodada — é a promessa do tipo
    memoria.apagar_da_tarefa(os.path.join(DIARIO_DIR, diario.id + ".mem"))
    nao_rodaram = [i for i, n in faltam.items() if n > 0]
    fim = diario.escrever("fim", nos_executados=feitos,
                          nao_rodaram=nao_rodaram,
                          falhas=[i for i, r in resultado.items() if not r.get("ok")])
    conta(fim)
    return {"diario": diario.id, "modo": modo, "resultado": resultado,
            "executados": feitos, "nao_rodaram": nao_rodaram}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    caminho = sys.argv[1]
    quer_valendo = "--valendo" in sys.argv
    fluxo = carregar(caminho)

    pode, modo, recados = guarda.liberado_pra_rodar(fluxo, forcar_ensaio=not quer_valendo)
    print(f"\n═══ {fluxo.get('nome', caminho)} ═══")
    for r in recados:
        print("  " + r)
    if not pode:
        return 1

    print()
    def mostrar(reg):
        if reg["evento"] == "começou":
            print(f"  ▸ {reg['titulo']}", flush=True)
        elif reg["evento"] == "terminou":
            print(f"    {'✅' if reg.get('ok') else '❌'} {reg.get('saida','')[:400]}")
        elif reg["evento"] == "pulou":
            print(f"  ⤵︎ pulou {reg['no']} — {reg['motivo']}")
        elif reg["evento"] == "gate":
            print(f"    🔴 {reg.get('saida')} ({', '.join(reg.get('motivos', []))})")
        elif reg["evento"] == "parado":
            print(f"  🛑 {reg['motivo']}")

    out = rodar(fluxo, modo, ao_vivo=mostrar)
    print(f"\n  {out['executados']} nó(s) · diário: execucoes/{out['diario']}.jsonl")
    if out["nao_rodaram"]:
        print(f"  não rodaram: {', '.join(out['nao_rodaram'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
