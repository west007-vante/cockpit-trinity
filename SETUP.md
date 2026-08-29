# 🌉 A Ponte — Trinity

Painel compartilhado entre **Pyerri** e **Davi**. O que cada um constrói no
Claude Code aparece pro outro, ao vivo, sem ninguém precisar avisar. Com chat do lado.

**No ar:** https://west007-vante.github.io/cockpit-trinity/

## Instalar na sua máquina
Guia completo (feito pro Davi, serve pra qualquer um): [`setup/PONTE.md`](setup/PONTE.md)

```bash
git clone https://github.com/west007-vante/cockpit-trinity.git ~/trinity
cd ~/trinity/setup && python3 install_worklog.py <steve|rico|goggins>
```

Depois reinicia o Claude Code e cria sua conta no painel.

## Como está montado
| Peça | Onde |
|---|---|
| Painel (página única, sem build) | `index.html` |
| Hook que reporta o trabalho | `setup/worklog_hook.py` |
| Instalador (idempotente, faz backup) | `setup/install_worklog.py` |
| Guia do sócio | `setup/PONTE.md` |

**Banco:** schema `trinity` do projeto Supabase *Steve* (`rlrxeegnwjsmxwzoytiz`), isolado
de `public`, `syc` e `verso`.

**Segurança:** a chave pública da página **grava** o worklog (por uma função
`SECURITY DEFINER` que valida o dono) mas **não lê nada** — nem título, nem e-mail,
nem caminho de arquivo. Leitura só pra quem está logado. Provado: `permission denied`
com a chave pública nas views.

## Arquivado
`cockpit-v11.html` — o Cockpit Trinity completo de junho/2026 (8 abas, feed, esteira,
classificador, agentes por MCP). O banco dele foi embora; fica aqui como referência
pra quando quiser reviver o resto em cima do `trinity`.
