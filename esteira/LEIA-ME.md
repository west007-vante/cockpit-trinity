# A ESTEIRA

Editor de fluxo que **executa de verdade**. Você arrasta tarefas pro canvas, puxa fio de
uma pra outra, ramifica — e aquilo roda na sua máquina.

Os cartões vêm do quadro do Trello ao vivo. Não é cópia: é o mesmo quadro que você e o
Davi olham.

---

## Ligar

```bash
~/esteira/daemon.sh servidor
```

Abre em **http://127.0.0.1:7717**. Pra desligar: `./daemon.sh parar-servidor`.

> **Por que um servidor e não só um arquivo HTML:** se a chave do Trello estivesse dentro
> do `.html`, qualquer um que o abrisse teria escrita no quadro. O servidor guarda a chave,
> busca os cartões e entrega prontos. O navegador nunca vê credencial, e nunca executa nada
> na sua máquina — ele só **pede**, e quem roda é o motor, depois do guarda.

---

## Os três modelos (o nó Agente escolhe quem pensa)

| Modelo | Onde roda | Custo | Medido nesta máquina |
|---|---|---|---|
| ☁️ **Claude** | nuvem, sua conta | plano pago | — |
| 🏠 **gpt-oss-20b** | local (M5, MLX) | grátis | 38 tok/s · pico 12,2 GB |
| 🎨 **FLUX.2-klein** | local (mflux) | grátis | 18,8 s por imagem 768² |

**A regra dos 24 GB:** texto e imagem locais nunca rodam juntos — a tranca serializa, e
imagem derruba o servidor de texto antes (ele volta sozinho no próximo uso).
`python3 modelos.py --estado` mostra; `--derrubar` libera a RAM na mão.

O nó Agente também escolhe **contexto** (pasta, cofre Obsidian com busca, card do quadro,
arquivo) e **memória** (comum · da tarefa · isolada) — tudo na gaveta do nó.

## Os seis tipos de nó

| | O que faz ao executar |
|---|---|
| 📋 **Tarefa** | mexe num cartão do quadro: move de lista, comenta |
| 🤖 **Agente** | dispara `claude -p "<seu pedido>"` na pasta que o nó declarar |
| ⚡ **Comando** | roda um comando de terminal |
| ❓ **Condição** | ramifica: sai pelo ✅ ou pelo ❌ conforme o passo anterior |
| ⏱️ **Espera** | segura X minutos |
| 🔀 **Dividir** | solta vários caminhos ao mesmo tempo |

**O fio** liga a saída de um nó à entrada de outro: *"quando aquele terminar, começa este"*.
Da condição saem dois fios, um por porta.

**Gestos:** arraste um tipo da lateral pro canvas · puxe a bolinha da direita até outro nó
pra ligar · clique no fio pra cortar · `Delete` apaga o nó selecionado · `Ctrl`+roda dá zoom
· arrastar o fundo move a tela.

---

## 🎭 Ensaio e ▶️ Valendo

**Todo fluxo nasce em ensaio.** No ensaio ele descreve o que faria, passo a passo, e **não
faz nada**: não abre processo, não chama o agente, não toca no Trello.

Pra executar de verdade você solta o fluxo — botão 🔒 na barra. Fica gravado **quem soltou
e quando**, dentro do próprio arquivo do fluxo.

Isso não é burocracia. Um fluxo que dispara prompts de IA e comandos de terminal roda com
todo o seu acesso: seus arquivos, suas contas, seus marketplaces. Você vai querer ver o
ensaio antes.

---

## Os sete freios

Todos vivem em `guarda.py`, testáveis sozinhos: `python3 guarda.py` roda 22 provas sem
executar nada.

1. **Ensaio por padrão** — fluxo sem liberação explícita não executa. Arquivo corrompido,
   campo faltando ou fluxo novo: todos caem em ensaio.
2. **Gate gravado** — soltar deixa nome e data no arquivo.
3. **Teto de rodada** — 40 nós no máximo, timeout por nó, e **ciclo barrado antes de
   começar**: um fluxo que se morde não chega a rodar.
4. **Pasta declarada** — cada nó de agente ou comando diz onde roda. Fora das casas
   permitidas (`CASAS_PERMITIDAS`), recusa. Escapar com `..` não funciona.
5. **Lista vermelha** — `rm -rf`, `sudo`, `git push`, `DELETE FROM`, publicar, mandar
   mensagem: **param e pedem você**, mesmo num fluxo já solto.
6. **Diário** — cada rodada grava tudo em `execucoes/`. Nada roda sem rastro.
7. **Parar tudo** — `./daemon.sh parar-tudo`. Nenhum fluxo roda até você soltar o freio,
   nem os liberados, e a rodada em curso para no próximo nó.

---

## Comandos

```bash
~/esteira/daemon.sh estado
```

Mostra o servidor, o freio, os fluxos (quais estão soltos) e as últimas rodadas.

```bash
~/esteira/daemon.sh parar-tudo
```

O botão de pânico. Não pede confirmação — quem digita isso está com pressa.

```bash
~/esteira/daemon.sh diario
```

O passo a passo da última rodada.

```bash
python3 ~/esteira/motor.py fluxos/meu.json
```

Roda pelo terminal (ensaio; `--valendo` pra executar).

---

## As peças

| Arquivo | O que é |
|---|---|
| `guarda.py` | os sete freios · `python3 guarda.py` prova todos |
| `motor.py` | executa o fluxo: ordem topológica, os 6 tipos, o diário |
| `servidor.py` | serve o canvas e guarda a chave do Trello |
| `esteira.html` | o canvas — design herdado do `~/quadro/canvas-obra.html` |
| `daemon.sh` | ligar, desligar, espiar, **parar tudo** |
| `fluxos/*.json` | um arquivo por fluxo |
| `execucoes/*.jsonl` | o diário de cada rodada |

Não toca em nada do `~/trinity/trello/` — só lê o quadro por ele. Se a ESTEIRA quebrar, o
quadro continua vivo.
