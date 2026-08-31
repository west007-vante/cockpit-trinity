#!/usr/bin/env python3
"""TERMINAIS VIVOS — shells de verdade morando no canvas da ESTEIRA.

Não é emulação nem controle remoto: cada card é um PTY real com o SEU zsh,
rodando NESTA máquina — o mesmo processo que o Terminal.app te daria. O canvas
é só a janela. (A cara do Maestri, dentro do nosso sistema — pedido do dono.)

Vivem enquanto o servidor viver (launchd segura o servidor; reiniciar o
servidor fecha os shells — igual fechar o app de terminal).
"""
import base64
import fcntl
import secrets
import os
import pty
import signal
import struct
import subprocess
import termios
import threading
import time

TERMS = {}
_SEQ = {"n": 0}
_LOCK = threading.Lock()
CAP = 400_000          # bytes de história por terminal — além disso, esquece o começo


def criar(nome="terminal", pasta="~", x=200, y=200):
    with _LOCK:
        _SEQ["n"] += 1
        # id único ENTRE reinícios do servidor: a página do canvas sobrevive ao
        # boot e um "t1" novo colidiria com o "t1" morto que ela ainda mostra
        tid = f"t{_SEQ['n']}-{secrets.token_hex(3)}"
    master, slave = pty.openpty()
    env = dict(os.environ)
    env.update(TERM="xterm-256color", LANG=env.get("LANG") or "pt_BR.UTF-8",
               ESTEIRA_TERMINAL=tid)
    shell = env.get("SHELL") or "/bin/zsh"
    proc = subprocess.Popen(
        [shell, "-il"],                       # interativo + login: o zsh de verdade, com o seu perfil
        stdin=slave, stdout=slave, stderr=slave,
        cwd=os.path.expanduser(pasta or "~"),
        env=env, start_new_session=True, close_fds=True)
    os.close(slave)
    t = {"id": tid, "nome": nome or "terminal", "pasta": pasta, "x": x, "y": y,
         "master": master, "proc": proc, "buf": bytearray(), "base": 0,
         "vivo": True, "criado": time.strftime("%H:%M")}
    TERMS[tid] = t

    def ler():
        while True:
            try:
                dados = os.read(master, 65536)
            except OSError:
                break
            if not dados:
                break
            with _LOCK:
                t["buf"] += dados
                if len(t["buf"]) > CAP:
                    corta = len(t["buf"]) - CAP
                    t["base"] += corta
                    del t["buf"][:corta]
        t["vivo"] = False

    threading.Thread(target=ler, daemon=True).start()
    return {"id": tid, "nome": t["nome"], "x": x, "y": y}


def entrada(tid, texto_b64):
    t = TERMS.get(tid)
    if not t or not t["vivo"]:
        return False
    try:
        os.write(t["master"], base64.b64decode(texto_b64))
        return True
    except OSError:
        return False


def saida(tid, desde):
    """O que o shell falou desde a posição `desde` (offset absoluto)."""
    t = TERMS.get(tid)
    if not t:
        return None
    with _LOCK:
        base, buf = t["base"], bytes(t["buf"])
    fim = base + len(buf)
    ini = max(int(desde or 0), base)
    pedaco = buf[ini - base:] if ini < fim else b""
    return {"desde": fim, "dados": base64.b64encode(pedaco).decode(),
            "vivo": t["vivo"]}


def tamanho(tid, cols, rows):
    t = TERMS.get(tid)
    if not t or not t["vivo"]:
        return False
    try:
        fcntl.ioctl(t["master"], termios.TIOCSWINSZ,
                    struct.pack("HHHH", max(2, int(rows)), max(2, int(cols)), 0, 0))
        os.kill(t["proc"].pid, signal.SIGWINCH)
        return True
    except Exception:
        return False


def mover(tid, x, y, nome=None):
    t = TERMS.get(tid)
    if not t:
        return False
    t["x"], t["y"] = int(x), int(y)
    if nome:
        t["nome"] = str(nome)[:60]
    return True


def fechar(tid):
    t = TERMS.pop(tid, None)
    if not t:
        return False
    try:
        os.killpg(os.getpgid(t["proc"].pid), signal.SIGHUP)
    except Exception:
        pass
    try:
        os.close(t["master"])
    except Exception:
        pass
    return True


def lista():
    return [{"id": t["id"], "nome": t["nome"], "x": t["x"], "y": t["y"],
             "vivo": t["vivo"], "criado": t["criado"], "pasta": t.get("pasta")}
            for t in TERMS.values()]


if __name__ == "__main__":
    print("── prova sem navegador: um shell de verdade ──")
    info = criar("prova", "~/esteira")
    tid = info["id"]
    time.sleep(1.2)
    entrada(tid, base64.b64encode(b"echo VIVO-$((21+21))\n").decode())
    time.sleep(1.0)
    s = saida(tid, 0)
    texto = base64.b64decode(s["dados"]).decode("utf-8", "replace")
    ok = "VIVO-42" in texto
    print(f"  {'✅' if ok else '❌'} o shell respondeu: procurando VIVO-42 → {'achou' if ok else texto[-200:]}")
    tamanho(tid, 120, 30)
    print(f"  ✅ redimensionado pra 120×30")
    fechar(tid)
    print(f"  ✅ fechado — processos não ficam órfãos")
    raise SystemExit(0 if ok else 1)
