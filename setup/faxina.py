#!/usr/bin/env python3
"""FAXINA — tira segredo de texto antes dele sair da máquina.

Roda ANTES de qualquer transcrição de sessão subir pra Ponte. Regra da casa:
nada com cheiro de chave, token ou senha atravessa a ponte em texto legível.

Filosofia: **errar pra mais**. É melhor mascarar um pedaço de base64 inocente
do que deixar passar uma service key. O que é mascarado vira `‹CHAVE-SUPABASE
mascarada›` — o leitor entende que existia algo ali, sem poder usar.

Uso:
    from faxina import limpar
    texto_limpo, quantos = limpar(texto)

    # ou pela linha de comando:
    python3 faxina.py arquivo.md > limpo.md
"""
import re
import sys

# Cada regra é (nome, regex, grupo_a_mascarar). grupo 0 = a coincidência inteira.
REGRAS = [
    # ── chaves de nuvem e API ─────────────────────────────────────────────
    ("CHAVE-SUPABASE",   re.compile(r"\bsb_(?:secret|publishable)_[A-Za-z0-9_\-]{8,}"), 0),
    ("JWT",              re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), 0),
    ("CHAVE-AWS",        re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), 0),
    ("TOKEN-GITHUB",     re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"), 0),
    ("CHAVE-OPENAI",     re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}"), 0),
    ("CHAVE-GOOGLE",     re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), 0),
    ("TOKEN-SLACK",      re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), 0),
    ("TOKEN-VERCEL",     re.compile(r"\bvercel_[A-Za-z0-9]{20,}"), 0),
    ("CHAVE-STRIPE",     re.compile(r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{16,}"), 0),
    ("CHAVE-PRIVADA",    re.compile(r"-----BEGIN[A-Z ]*PRIVATE KEY-----.*?-----END[A-Z ]*PRIVATE KEY-----", re.S), 0),

    # ── senha dentro de string de conexão: postgres://user:SENHA@host ─────
    ("SENHA-DE-CONEXAO", re.compile(r"(?<=://)([^:/\s@]+):([^@/\s]{3,})(?=@)"), 2),

    # ── atribuições: SENHA=..., "api_key": "...", "Senha database: ..." ───
    # O miolo `(?:[\w\-\.]|\s){0,24}` deixa passar palavra no meio — "senha do
    # banco:", "Senha database:", "chave de acesso =" — que era por onde a
    # senha do Davi escapava.
    ("SEGREDO",          re.compile(
        r"(?i)\b(?:secret|senha|password|passwd|api[_\-]?key|apikey|token|"
        r"service[_\-]?role|credential|private[_\-]?key|chave|pwd)"
        r"(?:[\w\-\.\"']|[ \t]){0,24}?"
        r"(\s*[:=]\s*|\s*=>\s*|[ \t]+(?:é|eh|is|era)[ \t]+)"
        r"(\"[^\"\n]{3,}\"|'[^'\n]{3,}'|[^\s,;'\"}\)\]]{3,})"), 2),

    # ── cabeçalho HTTP de autorização ─────────────────────────────────────
    ("AUTORIZACAO",      re.compile(r"(?i)\b(?:authorization|apikey|x-api-key)\s*:\s*(?:bearer\s+)?([^\s\"'\\]{6,})"), 1),
]

# Coisas que PARECEM segredo mas não são — não vale sujar o texto por elas.
INOCENTES = re.compile(
    r"(?i)^(?:null|none|true|false|undefined|xxx+|\.\.\.|<[^>]*>|\$\{[^}]*\}|"
    r"your[_\-]?\w*|exemplo|example|placeholder|senha|password|token|chave|key|"
    r"sua[_\-]?\w*|the[_\-]?\w*|mascarad[oa]|redacted)$"
)


def _vale_mascarar(valor: str) -> bool:
    v = valor.strip().strip("\"'")
    if len(v) < 6:
        return False
    if INOCENTES.match(v):
        return False
    if v.startswith("‹"):          # já mascarado numa passada anterior
        return False
    return True


def _parece_segredo(valor: str) -> bool:
    """Tem cara de credencial, e não de palavra da língua?

    Só é exigido quando o separador é natural ("a senha é X"), porque aí o
    texto pode ser uma frase comum — foi o que fez "a chave do sucesso é
    insistir" perder a palavra 'insistir'. Com `:` ou `=` seguimos agressivos.
    """
    v = valor.strip().strip("\"'")
    classes = sum([
        any(c.islower() for c in v),
        any(c.isupper() for c in v),
        any(c.isdigit() for c in v),
        any(not c.isalnum() for c in v),
    ])
    return classes >= 2 or len(v) >= 20


def limpar(texto: str):
    """Devolve (texto_limpo, quantidade_mascarada)."""
    if not texto:
        return texto, 0
    achados = []                    # (inicio, fim, rotulo)

    for nome, rx, grupo in REGRAS:
        for m in rx.finditer(texto):
            try:
                ini, fim = m.span(grupo)
            except IndexError:
                continue
            if ini < 0 or fim <= ini:
                continue
            if grupo != 0 and not _vale_mascarar(m.group(grupo)):
                continue
            # separador em linguagem natural ("a senha é X") exige que o valor
            # tenha cara de credencial — senão come palavra de frase comum
            if nome == "SEGREDO":
                separador = m.group(1) or ""
                if not re.match(r"^\s*[:=]|^\s*=>", separador) and not _parece_segredo(m.group(grupo)):
                    continue
            achados.append((ini, fim, nome))

    if not achados:
        return texto, 0

    # resolve sobreposição: quem começa antes ganha; empate, o trecho maior
    achados.sort(key=lambda a: (a[0], -(a[1] - a[0])))
    limpos, ultimo_fim = [], -1
    for ini, fim, nome in achados:
        if ini >= ultimo_fim:
            limpos.append((ini, fim, nome))
            ultimo_fim = fim

    pedacos, cursor = [], 0
    for ini, fim, nome in limpos:
        pedacos.append(texto[cursor:ini])
        pedacos.append(f"‹{nome} mascarad{'a' if nome.startswith(('CHAVE','SENHA','AUTORIZ')) else 'o'}›")
        cursor = fim
    pedacos.append(texto[cursor:])
    return "".join(pedacos), len(limpos)


if __name__ == "__main__":
    origem = open(sys.argv[1], encoding="utf-8").read() if len(sys.argv) > 1 else sys.stdin.read()
    saida, n = limpar(origem)
    sys.stdout.write(saida)
    print(f"\n<!-- faxina: {n} segredo(s) mascarado(s) -->", file=sys.stderr)
