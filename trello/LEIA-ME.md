# O QUADRO — a receita

Quadro vivo no Trello entre **Pyerri, Davi, Steve e Rico**. Alimentado sozinho
pelas sessões do Claude Code dos dois lados.

- **Manual do Davi:** [MANUAL-DAVI.md](MANUAL-DAVI.md) — manda esse link pra ele
- **Plano completo:** `~/.claude/plans/expressive-petting-haven.md`

---

## O modelo (o que confunde todo mundo)

```
   1 API key (o robô)  ─┬─►  token do Steve  ──►  escreve como Steve
                        └─►  token do Rico   ──►  escreve como Rico
                                                   ▲
   O QUADRO (1 só) ────────────────────────────────┘
   membros: Pyerri · Davi · Steve · Rico
```

- **API key** = identifica o *robô*. **Uma só**, pública por desenho. Mande pro Davi.
- **Token** = identifica *a pessoa*. Cada conta gera o seu. **Segredo.**
- **Quadro** = um só. Quem escreve nele é quem for **membro**.

E são **duas ligações diferentes** com o Trello, as duas necessárias:

| | O que é | Quando funciona |
|---|---|---|
| **API REST** (chave + token) | o robô alimentando o quadro | 24h, sozinho |
| **MCP** (`mcp.trello.com/v1`) | o Steve *conversando* com o quadro | só durante o papo |

---

## Ordem de ligação — lado do Pyerri

### 1. Crie o quadro na mão, logado como VOCÊ (não como o Steve)

No trello.com, com a sua conta pessoal, crie um quadro com este nome **exato**:

```
O QUADRO · Pyerri × Davi
```

> **Por que na mão e por que na sua conta:** assim o quadro é seu. Se um dia você
> revogar o robô, você não perde o quadro junto.

Convide, ali mesmo: **o Davi**, **o Steve** (pyerree5@) e **o Rico**.

### 2. Conecte esta máquina como Steve

```bash
python3 ~/trinity/trello/destravar.py --como steve
```

Ele pede a API key e o token. ⚠️ Gere o token **logado como Steve** — janela
anônima resolve. Ele confere o nome e reclama se não bater.

### 3. Monte as listas e etiquetas

```bash
python3 ~/trinity/trello/bootstrap_board.py --conferir
```

```bash
python3 ~/trinity/trello/bootstrap_board.py --limpar
```

O `--limpar` arquiva as listas padrão vazias do Trello (To Do / Doing / Done).
Lista com card dentro ele **não** toca.

### 4. Suba as 53 tarefas do Quadro da Obra

```bash
python3 ~/trinity/trello/migrar_quadro.py --conferir
```

```bash
python3 ~/trinity/trello/migrar_quadro.py
```

### 5. Ligue o robô

```bash
bash ~/trinity/trello/daemon.sh start
```

### 6. Ligue o Steve no quadro (MCP)

```bash
claude mcp add --transport http trello https://mcp.trello.com/v1 --scope user
```

Autorize **como Steve**. Depois: *"Steve, o que eu tenho pra hoje?"*

### 7. Mande o manual pro Davi

O arquivo [MANUAL-DAVI.md](MANUAL-DAVI.md) + a API key. **Nunca o seu token.**

---

## As peças

| Arquivo | O que faz |
|---|---|
| `trello_api.py` | cliente REST do Trello (stdlib pura) |
| `classificador.py` | decide o balde de cada trabalho — **roda sem rede** |
| `cartao.py` | monta e lê o corpo do card |
| `comum.py` | nomes de listas, mapeamentos, índice do quadro |
| `destravar.py` | assistente de conexão (você clica, ele confere e guarda) |
| `bootstrap_board.py` | cria listas e etiquetas — idempotente |
| `migrar_quadro.py` | sobe o Quadro da Obra pro Trello |
| `roteador.py` | fila do worklog → card |
| `agendador.py` | estipula horário e joga na Google Agenda |
| `espelho_quadro.py` | Trello → `~/quadro/tasks.json` |
| `rotas.json` | **a tabela que você edita** — pasta→frente, janela de trabalho |
| `ciclo.sh` · `daemon.sh` | o robô de 10 em 10 minutos |
| `instalar.py` | instalação de uma tacada (usado pelo Davi) |

---

## O classificador — como ele decide

Quatro camadas. A mais burra é a que mais acerta.

1. **Mexeu ou não mexeu** — no hook. Conversa fiada morre aí. *(sua lei)*
2. **Os arquivos tocados decidem** — casa o caminho contra `rotas.json`.
   Usa os **arquivos**, não a pasta: quem trabalha sempre a partir da home tem
   o `cwd` igual em 100% das sessões — a pasta não classificaria nada.
3. **Palavra-chave no título** — só quando nenhum arquivo casou.
4. **Não casou → 📥 Entrada**, com o motivo escrito no card. Nunca chuta.

**Pra ensinar uma frente nova:** edite `rotas.json`. O robô relê a cada ciclo.

### O terceiro balde

Turno **só de pesquisa** (leu, buscou, não escreveu) acima de **5 min** e com pelo
menos **2 buscas** vira card na 🧪 Bancada. Um "que horas são" não passa.
Afrouxe ou aperte em `rotas.json` → `bancada_por_pesquisa`.

---

## Comandos do dia a dia

```bash
bash ~/trinity/trello/daemon.sh status
```

```bash
python3 ~/trinity/trello/roteador.py --conferir
```

Mostra **o que o robô faria** com a fila, sem fazer. É o melhor jeito de entender
por que um card caiu onde caiu — e de descobrir rota faltando.

```bash
bash ~/trinity/trello/daemon.sh now
```

---

## Limites que valem saber

- **Trello grátis não tem Calendário de verdade.** O Planner mostra os cards
  agendados mas é só leitura. Por isso a agenda de verdade é a Google.
- **Butler (automação do Trello) no grátis: 250 execuções/mês.** Nosso robô não
  usa Butler — esse limite fica todo pra regra que você criar na mão.
- **A API do Trello: 300 requisições por 10 s.** O robô já respeita, com pausa
  entre cards e repetição automática se levar 429.

---

## Segurança

- O token vive em `~/.steve/trello.env`, **chmod 600**. Nunca no git.
- O escopo pedido é `read,write` — **sem `account`**, então o robô não vê e-mail
  nem notificação de ninguém.
- **Pra cortar tudo na hora:** trello.com → conta → Settings → revogue o token.
  Não precisa mexer em código.
