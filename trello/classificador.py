#!/usr/bin/env python3
"""O classificador — decide em que balde cada trabalho cai.

Quatro camadas, da mais burra pra mais esperta. A burra é a que mais acerta.

  1. MEXEU OU NÃO MEXEU  (já vive no worklog_hook, antes daqui)
     Pergunta solta não chega neste arquivo. A lei do Pyerri, preservada.

  2. OS ARQUIVOS TOCADOS DECIDEM
     Cada arquivo escrito/editado é casado contra as rotas de rotas.json.
     Vence a rota com mais arquivos. Determinístico: mesma entrada, mesma saída.
     (Usar os ARQUIVOS e não a pasta é obrigatório — o Pyerri trabalha sempre da
     home, então o cwd é /Users/pyerri em 100% das sessões e não classifica nada.)

  3. PALAVRA-CHAVE NO TÍTULO
     Só entra quando nenhum arquivo casou — turno só de comando, por exemplo.

  4. NÃO CASOU → 📥 ENTRADA
     Nunca chuta. Card na Entrada pra ele triar, com o motivo escrito no card.

Funções puras: não tocam em rede nem em disco (fora ler rotas.json). Dá pra
testar o classificador inteiro sem Trello, sem Supabase e sem internet.
"""
import json
import os
import sys
import unicodedata

ROTAS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rotas.json")


def carregar_rotas(arquivo=ROTAS_FILE):
    """Lê a tabela de rotas. Na primeira vez ela não existe — o repo só traz o
    exemplo, porque o rotas.json real mapeia as pastas e os clientes de quem usa
    e o repo é público. Aqui a gente copia o exemplo e avisa o que falta fazer."""
    if not os.path.exists(arquivo):
        exemplo = os.path.join(os.path.dirname(arquivo), "rotas.exemplo.json")
        if os.path.exists(exemplo):
            import shutil
            shutil.copy(exemplo, arquivo)
            sys.stderr.write(
                f"\n⚠️  Criei {arquivo} a partir do exemplo.\n"
                "   Ele ainda aponta pra pastas de mentira (/Users/SEU_USUARIO/...),\n"
                "   então TUDO vai cair na lista 📥 Entrada até você editar.\n"
                "   Troque pelas suas pastas e sua janela de trabalho.\n\n")
    with open(arquivo, encoding="utf-8") as f:
        return json.load(f)


def _simples(t):
    """minúscula, sem acento — pra casar palavra-chave sem depender de como digitou."""
    t = (t or "").lower()
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _e_ruido(caminho, rotas):
    pref = (rotas.get("ignorar_arquivos") or {}).get("prefixos") or []
    return any(caminho.startswith(p) for p in pref)


def classificar(arquivos=None, titulo="", ferramentas=None, duracao_s=0, rotas=None):
    """Devolve o veredito. Sempre devolve algo — nunca levanta, nunca chuta.

    Retorno:
      tipo   : 'obra' | 'cliente' | 'bancada' | 'entrada'
      area   : 'A'…'I' ou None
      rotulo : nome legível da frente ("MERCADOR · Mercado Livre")
      motivo : por que caiu aí — vai escrito no card, pra você poder discordar
      camada : qual das 4 camadas decidiu
      confianca: 'alta' | 'media' | 'baixa'
    """
    rotas = rotas or carregar_rotas()
    arquivos = [a for a in (arquivos or []) if a]
    ferramentas = ferramentas or {}
    titulo_s = _simples(titulo)

    # ---------------------------------------------------------- camada 2: arquivos
    uteis = [a for a in arquivos if not _e_ruido(a, rotas)]
    placar = {}
    for a in uteis:
        for i, r in enumerate(rotas["rotas"]):
            if a.startswith(r["caminho"]):
                chave = (r["tipo"], r.get("area"), r["rotulo"])
                # i entra no placar como desempate: rota declarada antes ganha
                atual = placar.get(chave, (0, i))
                placar[chave] = (atual[0] + 1, min(atual[1], i))
                break                      # 1 arquivo conta pra 1 rota só

    if placar:
        (tipo, area, rotulo), (n, ordem) = max(
            placar.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
        empate = sum(1 for v in placar.values() if v[0] == n) > 1
        return {
            "tipo": tipo, "area": area, "rotulo": rotulo,
            "camada": "arquivos",
            "confianca": "media" if empate else "alta",
            "motivo": (f"{n} de {len(uteis)} arquivo(s) tocado(s) caíram em {rotulo}"
                       + (" (houve empate com outra frente)" if empate else "")),
        }

    # ------------------------------------------------- camada 3: palavra no título
    pc = rotas.get("palavras_chave") or {}
    for area, termos in (pc.get("obra") or {}).items():
        for termo in termos:
            if _simples(termo) in titulo_s:
                return {"tipo": "obra", "area": area,
                        "rotulo": _rotulo_da_area(area, rotas),
                        "camada": "palavra-chave", "confianca": "media",
                        "motivo": f'o título fala em "{termo}"'}
    for nome, termos in (pc.get("cliente") or {}).items():
        for termo in termos:
            if _simples(termo) in titulo_s:
                return {"tipo": "cliente", "area": None, "rotulo": nome,
                        "camada": "palavra-chave", "confianca": "media",
                        "motivo": f'o título fala em "{termo}"'}
    for termo in (pc.get("bancada") or []):
        if _simples(termo) in titulo_s:
            return {"tipo": "bancada", "area": None, "rotulo": "Bancada",
                    "camada": "palavra-chave", "confianca": "baixa",
                    "motivo": f'o título fala em "{termo}"'}

    # --------------------------------------------------------- camada 4: não sei
    if uteis:
        motivo = (f"{len(uteis)} arquivo(s) tocado(s), nenhum numa frente conhecida "
                  f"(o primeiro foi {uteis[0]}). Diga onde isso mora e eu aprendo.")
    else:
        motivo = "não mexeu em arquivo nenhum e o título não bate com nenhuma frente."
    return {"tipo": "entrada", "area": None, "rotulo": "A triar",
            "camada": "não casou", "confianca": "baixa", "motivo": motivo}


def _rotulo_da_area(area, rotas):
    for r in rotas["rotas"]:
        if r.get("area") == area and r["tipo"] == "obra":
            return r["rotulo"]
    return {"A": "MERCADOR · Mercado Livre", "B": "Shopee · Upseller", "C": "GF Cortes",
            "D": "VERSO · EcommerceVerso", "E": "Tikebum", "F": "Máquina Zero→Venda",
            "G": "Infra e decisões", "H": "Entrega Steve → Tikebum",
            "I": "A Cara do Steve · Comercial"}.get(area, "Obra")


def e_bancada_de_pesquisa(ferramentas=None, duracao_s=0, escreveu=False, rotas=None):
    """O terceiro balde que o Pyerri pediu.

    Hoje um turno de estudo puro (ele pesquisando, lendo, sem escrever nada) é
    descartado junto com o "bom dia". A regra nova salva o estudo sem inundar o
    quadro de conversa: precisa de tempo E de busca de verdade.

    Um "que horas são" não passa. Uma hora estudando VRAM passa.
    """
    rotas = rotas or carregar_rotas()
    cfg = rotas.get("bancada_por_pesquisa") or {}
    if not cfg.get("ligado"):
        return False
    if escreveu:
        return False                       # escreveu = é obra, não bancada
    ferramentas = ferramentas or {}
    buscas = sum(v for k, v in ferramentas.items()
                 if k in ("WebSearch", "WebFetch", "Read", "Grep", "Glob"))
    return (duracao_s >= cfg.get("minutos_minimos", 5) * 60
            and buscas >= cfg.get("minimo_de_buscas", 2))


if __name__ == "__main__":
    # Bateria de prova — roda sem rede, sem Trello, sem nada.
    R = carregar_rotas()
    casos = [
        (["/Users/pyerri/mercador/lotes/x.json"], "publicar lote", "obra", "A"),
        (["/Users/pyerri/Desktop/Tikebum/app.tsx"], "ajustar tela", "cliente", None),
        (["/Users/pyerri/trinity/trello/roteador.py",
          "/Users/pyerri/trinity/trello/gcal.py"], "montar o quadro", "obra", "G"),
        (["/Users/pyerri/comfyui/wf.json"], "gerar imagem", "bancada", None),
        ([], "migrar anuncios do mercado livre", "obra", "A"),
        ([], "o Joaozinho pediu a NFC-e", "cliente", None),
        ([], "so uma curiosidade sobre isso", "bancada", None),
        (["/Users/pyerri/Music/x.mp3"], "mexer em som", "entrada", None),
        # ruído de máquina não pode decidir rota nenhuma:
        (["/private/tmp/claude-501/x/scratchpad/a.py"], "rascunho", "entrada", None),
        ([], "", "entrada", None),
    ]
    ok = 0
    for arqs, tit, esperado_tipo, esperada_area in casos:
        v = classificar(arqs, tit, rotas=R)
        bate = v["tipo"] == esperado_tipo and (esperada_area is None or v["area"] == esperada_area)
        ok += bate
        print(f"{'✅' if bate else '❌'} {v['tipo']:8s} {str(v['area'] or '-'):2s} "
              f"[{v['camada']:13s}] {(tit or '(sem título)')[:38]:38s} → {v['rotulo']}")
        if not bate:
            print(f"    esperava {esperado_tipo}/{esperada_area}, veio {v['tipo']}/{v['area']}")
    print(f"\n{ok}/{len(casos)} casos corretos")

    print("\n--- regra da Bancada (turno de pesquisa) ---")
    provas = [
        ({"WebSearch": 3, "Read": 4}, 900, False, True,  "1h estudando, sem escrever"),
        ({"WebSearch": 1}, 60, False, False,             "1 busca em 1 minuto"),
        ({"WebSearch": 5}, 900, True,  False,            "pesquisou MAS escreveu → é obra"),
        ({}, 3600, False, False,                         "1h sem buscar nada"),
    ]
    ok2 = 0
    for fer, dur, escreveu, esperado, desc in provas:
        got = e_bancada_de_pesquisa(fer, dur, escreveu, R)
        ok2 += got == esperado
        print(f"{'✅' if got == esperado else '❌'} {str(got):5s} (esperado {esperado}) — {desc}")
    print(f"\n{ok2}/{len(provas)} regras corretas")
    raise SystemExit(0 if ok == len(casos) and ok2 == len(provas) else 1)
