# 🌉 A Ponte — pro Davi

> Cinco minutos, uma vez na vida. Depois nunca mais pensa nisso.

---

## O que é

Tudo que você **constrói** no Claude Code — cria arquivo, edita, roda comando — aparece
sozinho num painel que o Pyerri e você compartilham. Em tempo real. Sem você avisar nada,
sem preencher relatório, sem lembrar de nada.

E tem um chat do lado, pra combinar as coisas sem sair do mesmo lugar.

## O que **não** entra

- **Conversa não é registrada.** Pergunta e resposta pura — do tipo "como funciona X?",
  "me explica isso" — não gera nada. Só trabalho de verdade (Write, Edit, Bash).
- Não lê arquivo seu, não mexe em senha, não abre nada.
- O que sobe é: o que você pediu (o título), quantos arquivos mexeu, quantos comandos rodou.
- **Nunca trava seu Claude Code.** Se der problema, ele simplesmente não registra e segue.

> ⚠️ **O título da tarefa é a última coisa que você escreveu pro Claude.** Então o Pyerri lê
> o que você pediu. Se for mexer em algo particular, é só pausar (instruções no fim).

---

## Instalar

### 1. Clona o repositório

```bash
git clone https://github.com/west007-vante/cockpit-trinity.git ~/trinity
```

### 2. Roda o instalador — **a última palavra é `rico`**

```bash
cd ~/trinity/setup && python3 install_worklog.py rico
```

Tem que aparecer `✅ Worklog instalado.` Se apareceu, acabou.

### 3. Fecha e abre o Claude Code

`Cmd + Q` e abre de novo.

### 4. Cria sua conta no painel

Abre **https://west007-vante.github.io/cockpit-trinity/**, clica em
**"Primeira vez aqui? Criar minha conta"**, põe seu e-mail e uma senha sua.
Confirma pelo link que chega no e-mail, volta e entra.

Na primeira vez ele pergunta **quem é você** — escolhe **Davi**. Uma vez só.

---

## Conferir se pegou

Pede pro Claude Code criar um arquivo qualquer de teste. Abre o painel: seu nome
aparece na coluna da direita com uma bolinha laranja piscando. 🎉

---

## Atualizar depois

```bash
cd ~/trinity && git pull && python3 setup/install_worklog.py rico
```

Pode rodar quantas vezes quiser — não duplica nada.

---

## Pausar / desligar

**Pausar por um tempo** (o Claude Code segue normal, só não reporta):

```bash
mv ~/.steve/worklog.env ~/.steve/worklog.env.pausado
```

Pra voltar, inverte os nomes.

**Desligar de vez:** abre `~/.claude/settings.json`, tira as duas linhas que citam
`worklog_hook.py`, reinicia o Claude Code.

---

## Se der erro

**`command not found: python3`** → roda `xcode-select --install` e tenta de novo.

**`command not found: git`** → mesma coisa, `xcode-select --install` resolve.

**Qualquer outra coisa** → print da tela pro Pyerri. Não tem como quebrar nada:
o instalador faz backup antes de encostar em qualquer configuração sua.
