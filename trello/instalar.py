#!/usr/bin/env python3
"""Instalador do QUADRO — um comando só, dos dois lados.

    python3 instalar.py --como steve     (máquina do Pyerri)
    python3 instalar.py --como rico      (máquina do Davi)

O que ele faz, em ordem, parando no primeiro erro:
  1. confere Python e a pasta
  2. instala o hook do worklog e liga os ganchos no Claude Code
     (reaproveita o setup/install_worklog.py que já existia — não reescreve nada)
  3. conecta o Trello (chama o destravar.py — VOCÊ clica, ele só confere e guarda)
  4. liga o robô que roda a cada 10 min
  5. prova que funciona

Nada aqui faz login por você. Nenhum passo pede senha.
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
TRINITY = os.path.dirname(AQUI)
DONOS = ("steve", "rico", "goggins")


def passo(n, titulo):
    print(f"\n{'═' * 72}\n  PASSO {n} — {titulo}\n{'═' * 72}")


def rodar(cmd, entrada_interativa=False):
    print(f"  $ {' '.join(cmd)}\n")
    r = subprocess.run(cmd) if entrada_interativa else subprocess.run(cmd)
    return r.returncode == 0


def main():
    como = None
    for i, a in enumerate(sys.argv):
        if a == "--como" and i + 1 < len(sys.argv):
            como = sys.argv[i + 1].strip().lower()
    if como not in DONOS:
        print(__doc__)
        print(f"❌ diga quem é este lado: --como {' | '.join(DONOS)}")
        sys.exit(1)

    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║   O QUADRO — instalação da máquina de {como.upper():<31}║
╚══════════════════════════════════════════════════════════════════════╝""")

    # ---------------------------------------------------------------- passo 1
    passo(1, "conferindo a máquina")
    print(f"  python: {sys.version.split()[0]}")
    if sys.version_info < (3, 8):
        print("  ❌ precisa de Python 3.8 ou mais novo.")
        sys.exit(1)
    inst = os.path.join(TRINITY, "setup", "install_worklog.py")
    if not os.path.exists(inst):
        print(f"  ❌ não achei {inst}\n     você clonou o repo inteiro? "
              "git clone https://github.com/west007-vante/cockpit-trinity.git ~/trinity")
        sys.exit(1)
    print(f"  ✅ repo em {TRINITY}")

    # ---------------------------------------------------------------- passo 2
    passo(2, "o worklog — o que faz seu trabalho virar tarefa sozinho")
    print("""  Instala o hook no Claude Code. Depois disso, toda vez que você MEXER
  em alguma coisa (criar arquivo, rodar comando), aquilo vira tarefa.
  Conversa solta continua não virando nada.
""")
    if not rodar([sys.executable, inst, como]):
        print("  ❌ o instalador do worklog falhou. Pare aqui e me chame.")
        sys.exit(1)

    # ---------------------------------------------------------------- passo 3
    passo(3, "o Trello — conectar esta conta ao quadro")
    print(f"""  Agora o assistente vai te pedir duas coisas: a API key (a chave do robô,
  a MESMA dos dois lados — o Pyerri te manda) e o token de {como.upper()}
  (o segredo desta conta, que só você gera).

  ⚠️  Entre no Trello com a conta dedicada do {como.upper()} ANTES de clicar
      no link. O token sai no nome de quem estiver logado.
""")
    if not rodar([sys.executable, os.path.join(AQUI, "destravar.py"), "--como", como], True):
        print("  ❌ não conectou. Rode de novo: python3 trello/destravar.py --como " + como)
        sys.exit(1)

    # ---------------------------------------------------------------- passo 4
    passo(4, "ligar o robô")
    if not rodar(["bash", os.path.join(AQUI, "daemon.sh"), "start"]):
        print("  ⚠️  não consegui ligar o robô automaticamente.")
        print(f"     ligue na mão: bash {os.path.join(AQUI, 'daemon.sh')} start")

    # ---------------------------------------------------------------- passo 5
    passo(5, "a prova")
    rodar([sys.executable, os.path.join(AQUI, "destravar.py"), "--conferir"])

    print(f"""
{'═' * 72}
  PRONTO.

  ⚠️  REINICIE O CLAUDE CODE agora — o hook só vale em sessão nova.

  Daí em diante é automático. Pra espiar o robô:
      bash {AQUI}/daemon.sh status
      bash {AQUI}/daemon.sh now        (roda um ciclo agora)

  Pra ver o que ele FARIA sem fazer:
      python3 {AQUI}/roteador.py --conferir
{'═' * 72}""")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\n\ncancelado.")
