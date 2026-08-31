# O QUADRO — manual de conexão

**Pra quem:** Davi
**Tempo:** ~15 minutos
**O que você vai precisar:** a conta do Trello que você criou pro Rico, e a
**API key** que o Pyerri te mandou.

---

## O que é isso

Um quadro no Trello onde nós quatro — **Pyerri, Davi, Steve e Rico** — vemos o que
cada um está fazendo. A diferença pro Trello comum: **você não precisa criar card**.

Toda vez que você mexe em alguma coisa no Claude Code (cria arquivo, roda comando),
aquilo vira card sozinho, no seu nome, na frente certa. Conversa solta **não** vira
nada — a gente filtrou isso de propósito.

E o Rico passa a conseguir ler e escrever no quadro durante as suas conversas:
*"o que eu tenho pra hoje?"*, *"fecha o #E3"*.

---

## Antes de começar: entenda 3 coisas e o resto fica fácil

**1. A API key é do robô, não de ninguém.**
Ela identifica o *programa*. É a mesma pros dois lados. O Pyerri te manda ela sem
problema — a própria Atlassian diz que ela é pública por desenho.

**2. O token é seu. Ele é o segredo.**
O token identifica *quem o robô está representando*. Você gera o do **Rico**, na
conta do Rico. **Nunca mande seu token pra ninguém**, nem pro Pyerri.

**3. O quadro é um só, e você entra nele como membro.**
Não existe "ligar a API no quadro". Você aceita o convite, vira membro, e a partir
daí a sua chave escreve lá.

```
   1 API key (o robô)  ─┬─►  token do Steve  ──►  escreve como Steve
                        └─►  token do Rico   ──►  escreve como Rico
                                                   ▲
   O QUADRO (1 só) ────────────────────────────────┘
   membros: Pyerri · Davi · Steve · Rico
```

---

## PASSO 1 — aceite os dois convites

Você vai receber **dois** convites do Trello:

- um na **sua conta** (Davi)
- um na conta que você criou pro **Rico**

Aceite os dois. Sem isso, nada do resto funciona — o robô vai dar erro de permissão.

> Se não chegou, peça pro Pyerri reenviar. Olhe o spam.

---

## PASSO 2 — instale (um comando)

No terminal da sua máquina:

```bash
git clone https://github.com/west007-vante/cockpit-trinity.git ~/trinity
```

```bash
python3 ~/trinity/trello/instalar.py --como rico
```

O instalador vai te levar por 5 passos. **No passo 3 ele vai te pedir duas coisas:**

| O que ele pede | De onde vem |
|---|---|
| **API key** | o Pyerri te mandou |
| **token do Rico** | você gera, no link que ele mostrar |

> ### ⚠️ O erro que todo mundo comete aqui
> O token sai **no nome de quem estiver logado no Trello naquele navegador**.
> Se você estiver logado como Davi e clicar no link, vai gerar um token do *Davi*,
> e o robô vai assinar tudo com o nome errado.
>
> **Antes de clicar no link: abra uma janela anônima e entre com a conta do Rico.**
> Cole o link lá.
>
> O instalador confere isso e te avisa se o nome não bater. Se avisar, refaça.

No fim ele mostra:

```
✅ token válido — agindo como Rico (@rico...)
   quadro: O QUADRO · Pyerri × Davi → https://trello.com/b/...
```

Se apareceu isso, está feito.

**Depois: reinicie o Claude Code.** O hook só vale em sessão nova.

---

## PASSO 3 — ligue o Rico no quadro (o MCP)

Os passos acima fazem o **robô** escrever no quadro sozinho. Este passo é outra
coisa: faz o **Rico conversar** com o quadro durante o seu papo com ele.

```bash
claude mcp add --transport http trello https://mcp.trello.com/v1 --scope user
```

Na primeira vez que você usar, ele abre o navegador pedindo autorização.
**Autorize com a conta do Rico**, mesma regra da janela anônima.

Depois disso você pode falar com ele normalmente:

> *"o que eu tenho no quadro pra hoje?"*
> *"move o card do frontend pra Fazendo"*
> *"cria um card pro Pyerri: revisar o contrato"*

---

## Como funciona no dia a dia

Você não faz nada. Trabalha normal.

| O que você fez | O que aparece no quadro |
|---|---|
| mexeu em arquivo, rodou comando | card na frente certa, no seu nome |
| ficou 20 min pesquisando, sem escrever | card na 🧪 **Bancada** |
| perguntou uma coisa e seguiu a vida | **nada**. E é pra ser assim |
| mexeu em algo que o robô não conhece | card na 📥 **Entrada**, com o motivo escrito |

**O título do card é a última coisa que você escreveu pro Claude.** Ou seja: o
Pyerri lê o que você pediu. Vale lembrar disso antes de xingar o computador.

### As listas

| Lista | O que é |
|---|---|
| 📥 Entrada | o robô não soube classificar — alguém tria |
| 📋 Tarefas | a fila: existe, não é pra hoje |
| 🗓️ Hoje | agendado pra hoje |
| 🔨 Fazendo | em execução agora |
| ⏸️ Parado | travado esperando alguém |
| 🕐 Adiado | volta numa data futura |
| ✅ Feito · 🗑️ Descartado | fim de linha |
| 👥 Clientes | um card por cliente |
| 🧪 Bancada | curiosidade, hobby, experimento |

O robô **nunca** mexe sozinho em Parado, Adiado e Descartado. Decisão humana mora lá.

---

## Comandos que resolvem 90% dos problemas

```bash
bash ~/trinity/trello/daemon.sh status
```

```bash
python3 ~/trinity/trello/roteador.py --conferir
```

O segundo mostra **o que o robô faria** com o que está na fila, sem fazer nada.
É o melhor jeito de entender por que um card caiu onde caiu.

```bash
bash ~/trinity/trello/daemon.sh now
```

Roda um ciclo agora, sem esperar os 10 minutos.

---

## Se der problema

| Sintoma | O que é | Como resolve |
|---|---|---|
| `401 — token recusado` | token errado, expirado ou revogado | `python3 ~/trinity/trello/destravar.py --como rico` |
| Nada aparece no quadro | não reiniciou o Claude Code | reinicie e trabalhe uma vez |
| Card no nome errado | gerou o token logado como Davi | refaça o passo 2 na janela anônima |
| `a lista … não existe` | o Pyerri ainda não criou o quadro | fale com ele |
| Tudo cai na 📥 Entrada | o robô não conhece suas pastas | edite o `rotas.json` (abaixo) |

### ⚠️ A última linha é a mais importante — faça isso no primeiro dia

O robô decide o balde de cada trabalho pelas **pastas que você tocou**. Na primeira
execução ele cria `~/trinity/trello/rotas.json` a partir de um exemplo genérico, que
aponta pra pastas de mentira (`/Users/SEU_USUARIO/...`). **Até você editar, TUDO cai
na 📥 Entrada.**

Abra o arquivo e troque pelas suas pastas de verdade:

```bash
open -e ~/trinity/trello/rotas.json
```

Três coisas pra ajustar:

1. **`rotas`** — o caminho de cada projeto seu e em que frente ele cai
2. **`janela_de_trabalho.rico`** — seu horário real (o agendador usa isso)
3. **`palavras_chave`** — só se você quiser afinar

Depois, veja o efeito sem fazer nada:

```bash
python3 ~/trinity/trello/roteador.py --conferir
```

Se ainda cair na Entrada, me manda a saída desse comando que a gente acerta junto.

> O `rotas.json` fica **fora do git** de propósito: ele mapeia suas pastas e seus
> clientes, e o repo é público. Cada máquina tem o seu.

---

## O que fica na sua máquina

| Onde | O quê |
|---|---|
| `~/trinity/` | o código (é público, está no GitHub) |
| `~/.steve/trello.env` | **seu token** — só você lê (chmod 600) |
| `~/.steve/worklog.env` | credencial do worklog |
| `~/.claude/settings.json` | os ganchos (o instalador não apaga o que já tinha) |
| `~/.steve/quadro.log` | o diário do robô |

**Pra desligar tudo:** `bash ~/trinity/trello/daemon.sh stop`
**Pra revogar o acesso:** trello.com → sua conta → Settings → revogue o token.
Isso mata o robô na hora, sem precisar mexer em código.
