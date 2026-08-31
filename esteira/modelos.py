#!/usr/bin/env python3
"""O ROTEADOR DE MODELOS — quem pensa em cada nó, escolhido deliberadamente.

Três motores, três custos, três usos:

  claude        nuvem, sua conta paga.   Raciocínio pesado, código, ferramentas.
  local-texto   gpt-oss-20b no M5.       Classificar, resumir, redigir — de graça,
                                         inclusive de madrugada. 38 tok/s medidos.
  local-imagem  FLUX.2-klein via mflux.  Gerar imagem no meio do fluxo (~1m36s).

A REGRA DOS 24 GB: memória unificada — texto local (12 GB de pico medido) e
imagem local (~8 GB) NÃO rodam juntos. O lock serializa: o segundo espera.
`claude` não entra no lock (o peso dele mora na nuvem).

    python3 modelos.py --provar          # sobe o local, pergunta, mostra tok/s
    python3 modelos.py --derrubar        # derruba o servidor local (libera RAM)
    python3 modelos.py --estado
"""
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

CASA = os.path.dirname(os.path.abspath(__file__))
REGISTRO = os.path.join(CASA, "modelos.json")
LOCK = os.path.expanduser("~/.steve/modelo.lock")
ULTIMO_USO = os.path.expanduser("~/.steve/modelo-ultimo-uso")
PORTA_LOCAL = 8090
MLX_SERVER = os.path.expanduser("~/.local/bin/mlx_lm.server")

PADRAO = {
    "claude": {
        "tipo": "nuvem", "rotulo": "Claude (nuvem · conta paga)",
        "quando_usar": "raciocínio pesado, código, agente com ferramentas"},
    "local-texto": {
        "tipo": "texto-local", "rotulo": "gpt-oss-20b (local · grátis)",
        "hf": "mlx-community/gpt-oss-20b-MXFP4-Q8",
        "quando_usar": "classificar, resumir, redigir, madrugada"},
    "local-imagem": {
        "tipo": "imagem-local", "rotulo": "FLUX.2-klein (local · imagem)",
        "quando_usar": "gerar imagem no meio do fluxo"},
}


def registro():
    if os.path.exists(REGISTRO):
        try:
            return json.load(open(REGISTRO, encoding="utf-8"))
        except Exception:
            pass
    return dict(PADRAO)


class TrancaDeRAM:
    """Um modelo local por vez. flock: se o processo morrer, a tranca solta
    sozinha — sem arquivo-fantasma travando a esteira pra sempre."""

    def __init__(self):
        os.makedirs(os.path.dirname(LOCK), exist_ok=True)
        self.f = None

    def __enter__(self):
        self.f = open(LOCK, "w")
        fcntl.flock(self.f, fcntl.LOCK_EX)      # bloqueia até a vez chegar
        self.f.write(f"{os.getpid()} {time.strftime('%H:%M:%S')}\n")
        self.f.flush()
        return self

    def __exit__(self, *a):
        try:
            fcntl.flock(self.f, fcntl.LOCK_UN)
            self.f.close()
        except Exception:
            pass


# ─────────────────────────────────────────────── o servidor de texto local
def _local_no_ar():
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORTA_LOCAL}/v1/models", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def garantir_local(hf_modelo):
    """Sobe o mlx_lm.server se não estiver de pé. Primeiro boot carrega 12 GB
    pra RAM — dá até 90 s de espera antes de desistir."""
    if _local_no_ar():
        return True
    if not os.path.exists(MLX_SERVER):
        raise RuntimeError("mlx_lm.server não está instalado (uv tool install mlx-lm)")
    # stdin=DEVNULL é obrigatório: sem ele o servidor herda o stdin de quem o
    # chamou e segura o terminal/pipe do chamador aberto pra sempre — o daemon
    # "funciona" mas pendura a sessão que o pariu. Aconteceu; não repete.
    subprocess.Popen(
        [MLX_SERVER, "--model", hf_modelo, "--port", str(PORTA_LOCAL), "--host", "127.0.0.1"],
        stdin=subprocess.DEVNULL,
        stdout=open(os.path.join(CASA, "modelo-local.log"), "a"),
        stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(90):
        time.sleep(1)
        if _local_no_ar():
            return True
    raise RuntimeError("o servidor local não subiu em 90 s — veja ~/esteira/modelo-local.log")


def derrubar_local():
    r = subprocess.run(["pkill", "-f", "mlx_lm.server"], capture_output=True)
    return r.returncode == 0


def _marcar_uso():
    try:
        open(ULTIMO_USO, "w").write(str(int(time.time())))
    except Exception:
        pass


def derrubar_se_ocioso(minutos=10):
    """Chamado pelo laço do daemon: 12 GB parados na RAM não são aluguel grátis."""
    if not _local_no_ar():
        return False
    try:
        parado = time.time() - int(open(ULTIMO_USO).read().strip())
    except Exception:
        parado = 10 ** 9
    if parado > minutos * 60:
        derrubar_local()
        return True
    return False


# ─────────────────────────────────────────────────────── as três chamadas
def _limpar_harmony(texto):
    """O gpt-oss fala no formato harmony (canais de raciocínio). Se o canal
    vazar no content, fica só a resposta final — o raciocínio não é resposta."""
    if "<|channel|>final<|message|>" in texto:
        texto = texto.split("<|channel|>final<|message|>")[-1]
    for lixo in ("<|return|>", "<|end|>", "<|message|>"):
        texto = texto.replace(lixo, "")
    return texto.strip()


def chamar(modelo, pedido, pasta="~", timeout_s=300, saida_imagem=None):
    """A porta única. Devolve {"ok", "saida", "modelo", "duracao_s", ...}."""
    reg = registro()
    cfg = reg.get(modelo)
    if not cfg:
        return {"ok": False, "modelo": modelo,
                "saida": f"modelo desconhecido: {modelo!r}. Tenho: {', '.join(reg)}"}
    t0 = time.time()
    pasta = os.path.expanduser(pasta)

    # ── nuvem: o caminho de sempre
    if cfg["tipo"] == "nuvem":
        try:
            r = subprocess.run(["claude", "-p", pedido], cwd=pasta,
                               capture_output=True, text=True, timeout=timeout_s)
            return {"ok": r.returncode == 0, "modelo": modelo,
                    "saida": ((r.stdout or "") + (r.stderr or ""))[:8000],
                    "duracao_s": round(time.time() - t0, 1)}
        except subprocess.TimeoutExpired:
            return {"ok": False, "modelo": modelo, "saida": f"passou de {timeout_s}s"}
        except FileNotFoundError:
            return {"ok": False, "modelo": modelo, "saida": "`claude` não está no PATH"}

    # ── texto local: sobe o servidor (na tranca) e conversa OpenAI-compat
    if cfg["tipo"] == "texto-local":
        with TrancaDeRAM():
            try:
                garantir_local(cfg["hf"])
                corpo = json.dumps({
                    "model": cfg["hf"],
                    "messages": [{"role": "user", "content": pedido}],
                    "max_tokens": 2048, "temperature": 0.4,
                }).encode()
                req = urllib.request.Request(
                    f"http://127.0.0.1:{PORTA_LOCAL}/v1/chat/completions",
                    data=corpo, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=timeout_s) as r:
                    d = json.loads(r.read().decode())
                _marcar_uso()
                texto = _limpar_harmony(
                    (d.get("choices") or [{}])[0].get("message", {}).get("content", ""))
                uso = d.get("usage") or {}
                return {"ok": True, "modelo": modelo, "saida": texto,
                        "tokens": uso.get("completion_tokens"),
                        "duracao_s": round(time.time() - t0, 1)}
            except Exception as e:
                return {"ok": False, "modelo": modelo, "saida": f"local-texto falhou: {e}",
                        "duracao_s": round(time.time() - t0, 1)}

    # ── imagem local: mflux na linha de comando (a pilha já provada da casa)
    if cfg["tipo"] == "imagem-local":
        destino = os.path.expanduser(
            saida_imagem or f"~/esteira/execucoes/img-{int(time.time())}.png")
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        with TrancaDeRAM():
            # A regra dos 24 GB, na prática: o servidor de texto RESIDENTE ocupa
            # ~12 GB mesmo parado. Imagem em cima disso estoura. Então imagem
            # derruba o texto primeiro; o texto re-sobe sozinho no próximo uso.
            if _local_no_ar():
                derrubar_local()
                time.sleep(2)
            try:
                # FLUX.2 tem binário próprio (mflux-generate-flux2) e o nome
                # do modelo é minúsculo com o tamanho: flux2-klein-4b
                r = subprocess.run(
                    [os.path.expanduser("~/.local/bin/mflux-generate-flux2"),
                     "--model", "flux2-klein-4b", "--prompt", pedido,
                     "--steps", "4", "--width", "768", "--height", "768",
                     "--output", destino],
                    capture_output=True, text=True, timeout=max(timeout_s, 600))
                ok = r.returncode == 0 and os.path.exists(destino)
                return {"ok": ok, "modelo": modelo,
                        "saida": destino if ok else (r.stderr or r.stdout)[-1500:],
                        "imagem": destino if ok else None,
                        "duracao_s": round(time.time() - t0, 1)}
            except subprocess.TimeoutExpired:
                return {"ok": False, "modelo": modelo, "saida": "imagem estourou o tempo"}
            except FileNotFoundError:
                return {"ok": False, "modelo": modelo, "saida": "mflux-generate não está no PATH"}

    return {"ok": False, "modelo": modelo, "saida": f"tipo desconhecido: {cfg['tipo']}"}


if __name__ == "__main__":
    if "--derrubar" in sys.argv:
        print("⏹ derrubado" if derrubar_local() else "não estava de pé")
    elif "--estado" in sys.argv:
        print(f"servidor local: {'🟢 no ar' if _local_no_ar() else '⚪️ parado'}")
        for nome, cfg in registro().items():
            print(f"  {nome:14s} {cfg['rotulo']}")
    elif "--provar" in sys.argv:
        print("── prova do local-texto (sobe o servidor, pergunta, mede) ──")
        r = chamar("local-texto",
                   "Em uma frase curta em português: para que serve uma fila de tarefas?")
        print(f"  ok={r['ok']} · {r.get('duracao_s')}s · {r.get('tokens')} tokens")
        print(f"  resposta: {r['saida'][:220]}")
        sys.exit(0 if r["ok"] else 1)
    else:
        print(__doc__)
