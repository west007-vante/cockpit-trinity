#!/usr/bin/env python3
"""Assistente de conexão — leva você pelos passos e guarda as credenciais.

NÃO faz login por você. Login, autorização e consentimento são atos do dono da
conta — sempre. O que ele faz é montar o link certo, conferir o que voltou e
guardar no lugar certo, com a permissão certa.

O modelo, que confunde todo mundo:
    · a API KEY identifica o ROBÔ. É uma só, é pública por desenho, e a mesma
      serve pro Steve e pro Rico. Pode mandar pro Davi tranquilo.
    · o TOKEN identifica A PESSOA. Cada conta gera o seu. É SEGREDO.
    · o QUADRO é um só. Quem escreve nele é quem for MEMBRO dele.

    python3 destravar.py                 # conecta esta máquina
    python3 destravar.py --como rico     # o lado do Davi
    python3 destravar.py --link          # só imprime o link de autorização
    python3 destravar.py --conferir      # testa o que já está guardado
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trello_api import ENV_FILE, Trello, TrelloErro, carregar_env   # noqa: E402
from bootstrap_board import gravar_env                              # noqa: E402

PAINEL = "https://trello.com/apps/admin"


def link_de_autorizacao(key, nome_do_robo="O QUADRO (Steve e Rico)"):
    """expiration=never porque isto é um daemon: token que expira derruba o robô
    às 3 da manhã sem ninguém pra reautorizar. Escopo read,write — SEM 'account',
    que daria acesso a e-mail e notificações. O robô não precisa disso."""
    p = {"expiration": "never", "scope": "read,write", "response_type": "token",
         "key": key, "name": nome_do_robo}
    return "https://trello.com/1/authorize?" + urllib.parse.urlencode(p)


def _perguntar(rotulo, atual=""):
    dica = f" [enter mantém {atual[:8]}…]" if atual else ""
    v = input(f"{rotulo}{dica}: ").strip()
    return v or atual


# Os três campos da tela do Trello são parecidos e é fácil colar o errado.
# O tamanho os separa sem precisar chamar a API:
#   Chave de API  32 caracteres hex   ← pública
#   Segredo       64 caracteres hex   ← SEGREDO, e o nosso sistema não usa
#   Token         começa com ATTA (ou 64 hex, no formato antigo)
def conferir_chave(v):
    v = (v or "").strip()
    if len(v) == 64 and all(c in "0123456789abcdefABCDEF" for c in v):
        return ("Isso tem 64 caracteres — é o SEGREDO, não a Chave de API.\n"
                "     A Chave de API tem 32 e fica logo ACIMA do Segredo na mesma tela.\n"
                "     (o Segredo a gente não usa em lugar nenhum — pode fechar essa parte)")
    if v.upper().startswith("ATTA"):
        return "Isso é um TOKEN, não a Chave de API. O token vai no passo 2."
    if len(v) != 32:
        return f"A Chave de API tem 32 caracteres; essa tem {len(v)}. Conferiu se copiou inteira?"
    return None


def conferir_token(v, key=""):
    v = (v or "").strip()
    if v and key and v == key:
        return "Você colou a Chave de API de novo. O token é o texto da OUTRA tela, depois do 'Allow'."
    if len(v) == 32:
        return ("Isso tem 32 caracteres — é a Chave de API, não o token.\n"
                "     O token aparece DEPOIS que você clica em 'Allow' no link acima.")
    if len(v) == 64 and all(c in "0123456789abcdefABCDEF" for c in v):
        return ("Isso tem 64 caracteres hex — é o SEGREDO da tela do Power-Up.\n"
                "     O token é outra coisa: ele nasce quando você clica em 'Allow' no link acima,\n"
                "     e no formato de hoje começa com 'ATTA'.")
    if len(v) < 40:
        return f"Token curto demais ({len(v)} caracteres). Copiou o texto inteiro da tela?"
    return None


def main():
    como = "steve"
    for i, a in enumerate(sys.argv):
        if a == "--como" and i + 1 < len(sys.argv):
            como = sys.argv[i + 1].strip().lower()

    cfg = carregar_env()

    # ------------------------------------------------------------ só conferir
    if "--conferir" in sys.argv:
        try:
            t = Trello()
            eu = t.eu()
            print(f"✅ token válido — agindo como {eu.get('fullName')} (@{eu.get('username')})")
            if t.board_id:
                b = t.board()
                print(f"   quadro: {b.get('name')} → {b.get('shortUrl')}")
                membros = ", ".join(f"@{m['username']}" for m in (t.membros() or []))
                print(f"   membros: {membros}")
            else:
                print("   ⚠️  sem TRELLO_BOARD_ID ainda — rode o bootstrap_board.py")
        except TrelloErro as e:
            print(f"❌ {e}")
            sys.exit(1)
        return

    # ----------------------------------------------------------- só revogar
    if "--revogar" in sys.argv:
        import getpass
        print("""
╔══════════════════════════════════════════════════════════════════════╗
║  REVOGAR UM TOKEN                                                    ║
╚══════════════════════════════════════════════════════════════════════╝

  Cole o token que você quer matar. Ele NÃO aparece na tela enquanto você
  digita, e não fica no histórico do terminal — por isso isto é um comando
  e não uma linha solta que você cola no shell.
""")
        alvo = getpass.getpass("  token a revogar (não aparece): ").strip()
        if not alvo:
            print("  nada informado. Nada foi feito.")
            return
        key = cfg.get("TRELLO_KEY") or _perguntar("  API key")
        try:
            # autentica COM o próprio token que está sendo morto: quem tem o
            # token tem o direito de matá-lo, e assim não precisamos de outro.
            Trello(key=key, token=alvo).revogar_token()
            print("  ✅ revogado. Esse token não serve mais pra nada.")
        except TrelloErro as e:
            # "invalid token" e "invalid app token" querem dizer a mesma coisa
            # pra quem está revogando: esse token não abre mais nada.
            if "invalid" in str(e).lower() and "token" in str(e).lower():
                print("  ✅ o Trello não reconhece esse token — ou já estava revogado,\n"
                      "     ou não era um token válido. De um jeito ou de outro, morto.")
            else:
                print(f"  ⚠️  {e}")
                print("     faça na mão: trello.com → seu avatar → Settings →\n"
                      "     Applications → Revoke")
        return

    # ------------------------------------------------------------- só o link
    if "--link" in sys.argv:
        key = cfg.get("TRELLO_KEY") or _perguntar("API key")
        print(link_de_autorizacao(key))
        return

    # ------------------------------------------------------------- o caminho
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  CONECTAR O QUADRO — este lado vai agir como: {como.upper():<23}║
╚══════════════════════════════════════════════════════════════════════╝

  Eu não faço login por você. Você clica, eu confiro e guardo.
""")

    # ---- passo 1: a chave do robô
    print("─" * 72)
    print("PASSO 1 — a API key (a chave do ROBÔ, uma só pros dois lados)")
    if cfg.get("TRELLO_KEY"):
        # Mandar criar Power-Up quando a chave já existe faz a pessoa criar um
        # segundo aplicativo à toa — ou pior, procurar na conta errada e achar
        # que está tudo perdido. A chave mora em UMA conta e serve pra todas.
        print(f"""
  Já tenho a chave guardada: {cfg['TRELLO_KEY'][:8]}…  → é só dar ENTER.

  ⚠️  Não vá procurar Power-Up na conta do {como.upper()}: a chave nasce em UMA
      conta só e vale pra todas. Se a tela 'Seus aplicativos' do {como} estiver
      vazia, está certo — não crie outro.
""")
    else:
        print(f"""
  Se você JÁ tem a chave, cole aqui embaixo e pule o resto do passo.

  Se não tem: abra {PAINEL}
    → 'New' e crie um Power-Up (nome: O QUADRO · workspace: o seu)
    → dentro dele, aba 'API Key' → 'Generate a new API Key'

  Essa chave é PÚBLICA por desenho — pode mandar pro Davi sem medo.
  Você cria UMA vez, na conta que quiser. Ela serve pro Steve e pro Rico.
""")
    while True:
        key = _perguntar("  cole a API key", cfg.get("TRELLO_KEY", ""))
        if not key:
            print("\n❌ sem a chave não dá pra seguir.")
            sys.exit(1)
        problema = conferir_chave(key)
        if not problema:
            break
        print(f"\n  ⚠️  {problema}\n")

    # ---- passo 2: o token da pessoa
    print("\n" + "─" * 72)
    print(f"PASSO 2 — o token de {como.upper()} (o SEGREDO desta conta)")
    print(f"""
  ⚠️  O token sai no nome de QUEM ESTIVER LOGADO NAQUELE NAVEGADOR.
      Não adianta querer o {como.upper()}: se o navegador está com outra conta,
      o token vem no nome dela e o robô assina tudo errado no histórico do card.

  FAÇA ASSIM, nesta ordem:

    1. abra uma JANELA ANÔNIMA   (⌘⇧N no Chrome)
    2. vá em  https://trello.com/login   e entre com a conta do {como.upper()}
    3. só então cole o link abaixo NA MESMA janela anônima
    4. a tela vai dizer em nome de quem está autorizando — CONFIRA ali
       antes de clicar em 'Allow'

  O link:
""")
    print("  " + link_de_autorizacao(key))
    print("""
  Depois do 'Allow' aparece um texto comprido numa página quase vazia.
  Aquilo é o token — hoje ele começa com 'ATTA'.
""")
    while True:
        token = _perguntar("  cole o token", cfg.get("TRELLO_TOKEN", ""))
        if not token:
            print("\n❌ sem o token não dá pra seguir.")
            sys.exit(1)
        problema = conferir_token(token, key)
        if not problema:
            break
        print(f"\n  ⚠️  {problema}\n")

    # ---- passo 3: conferir de verdade antes de guardar
    print("\n" + "─" * 72)
    print("PASSO 3 — conferindo…")
    try:
        t = Trello(key=key, token=token, board_id=cfg.get("TRELLO_BOARD_ID"))
        eu = t.eu()
    except TrelloErro as e:
        print(f"\n❌ {e}\n   nada foi gravado. Confira a chave e o token e rode de novo.")
        sys.exit(1)

    print(f"\n  ✅ funcionou — este lado vai agir como:")
    print(f"     {eu.get('fullName')}  (@{eu.get('username')})")
    if eu.get("email"):
        print(f"     {eu.get('email')}")

    esperado = {"steve": "steve", "rico": "rico"}.get(como)
    nome = f"{eu.get('fullName','')} {eu.get('username','')}".lower()
    if esperado and esperado not in nome:
        print(f"""
  ⚠️  ATENÇÃO: você pediu pra conectar como '{como}', mas o token voltou no nome
      de '{eu.get('username')}'. Se essa NÃO é a conta dedicada do {como},
      o navegador estava logado na conta errada na hora do 'Allow'.""")
        if input("\n  guardar assim mesmo? (s/N): ").strip().lower() != "s":
            print("  nada foi gravado.")
            # O token errado NÃO pode ficar vivo. Ele nasceu com escrita em todo
            # quadro daquela conta e sem prazo — largar ele solto é deixar uma
            # chave na fechadura. Oferecemos matar aqui, no calor do momento,
            # porque depois ninguém volta pra limpar.
            print(f"""
  Esse token que você acabou de gerar está VIVO: escrita em todo quadro
  de @{eu.get('username')}, sem data pra expirar. Deixar solto é chave na fechadura.""")
            if input("  quer que eu revogue ele agora? (S/n): ").strip().lower() in ("", "s"):
                try:
                    t.revogar_token()
                    print("  ✅ revogado. Ele não serve mais pra nada.")
                except TrelloErro as e:
                    print(f"  ⚠️  não consegui revogar ({e})")
                    print(f"     faça na mão: https://trello.com/u/{eu.get('username')}/account"
                          "  →  Applications  →  Revoke")
            else:
                print(f"     lembre de revogar depois: "
                      f"https://trello.com/u/{eu.get('username')}/account  →  Applications")
            print(f"\n  Pra refazer certo: janela anônima → trello.com/login como {como.upper()} "
                  f"→ só então o link.")
            return

    # ---- passo 4: guardar
    gravar_env("TRELLO_KEY", key)
    gravar_env("TRELLO_TOKEN", token)
    gravar_env("TRELLO_DONO", como)
    print(f"\n  ✅ guardado em {ENV_FILE} (só você lê: chmod 600)")

    # ---- passo 5: o que vem agora
    print("\n" + "─" * 72)
    if t.board_id:
        b = t.board()
        print(f"O quadro já existe: {b.get('name')} → {b.get('shortUrl')}")
        print("\npróximo passo:\n  python3 ~/trinity/trello/roteador.py --conferir")
    else:
        print("""Falta o quadro. Próximo passo:

  python3 ~/trinity/trello/bootstrap_board.py --conferir     (ver o que faria)
  python3 ~/trinity/trello/bootstrap_board.py                (criar de verdade)

⚠️  Crie o quadro com a SUA conta pessoal, não com a do robô — se um dia você
    revogar o robô, o quadro continua seu.""")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\ncancelado. Nada foi gravado.")
