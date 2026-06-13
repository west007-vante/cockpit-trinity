# 📣 Briefing pros sócios — "Worklog automático" no cockpit
> Pra mandar pro Davi e pro Murilo. Cada um faz UMA vez, leva 1 minuto.

---

## 🤔 O que é isso? (em 30 segundos)
Sabe tudo que você cria/faz dentro do Claude Code (cria arquivo, roda comando, builda algo)? A partir de agora **isso aparece SOZINHO no nosso cockpit** — na página inicial, na seção **"Trabalho da equipe"**.

Você **não precisa lembrar de nada**. Não precisa atualizar nada na mão. Terminou de fazer uma coisa no Claude Code → ela aparece pro time, em tempo real.

## 🎯 Por que a gente quer isso?
Pra **ninguém ficar no escuro**. Hoje, se o Davi passa o dia fazendo coisa e não avisa, o time não sabe. Com isso, a gente vê **quem tá fazendo o quê, ao vivo** — e se tá no caminho certo. É pra time render junto, não pra vigiar.

## 🔒 É seguro? (importante)
- ✅ Só registra **TRABALHO de verdade** (quando você cria/executa algo). **Conversa normal — pergunta e resposta — NÃO é registrada.** Sua privacidade de papo tá intacta.
- ✅ Não mexe nas suas senhas, não lê arquivo privado. Só monta um resuminho ("mexeu em 2 arquivos, rodou 3 comandos") + o que você pediu.
- ✅ **Nunca trava** o seu Claude Code. Se der qualquer problema, ele só não registra — e segue a vida.
- ✅ Dá pra desligar quando quiser (é só me avisar).

## 🛠️ Como instalar — PASSO A PASSO

### Passo 1 — Abre o Terminal
No Mac: aperta `Cmd + Espaço`, digita **Terminal**, Enter.

### Passo 2 — Cola o SEU comando (cada um tem o seu!) e dá Enter

**👉 DAVI, cola ISTO:**
```bash
mkdir -p ~/.steve && curl -fsSL https://raw.githubusercontent.com/west007-vante/cockpit-trinity/main/setup/worklog_hook.py -o ~/.steve/worklog_hook.py && curl -fsSL https://raw.githubusercontent.com/west007-vante/cockpit-trinity/main/setup/install_worklog.py -o ~/.steve/install_worklog.py && python3 ~/.steve/install_worklog.py rico
```

**👉 MURILO, cola ISTO:**
```bash
mkdir -p ~/.steve && curl -fsSL https://raw.githubusercontent.com/west007-vante/cockpit-trinity/main/setup/worklog_hook.py -o ~/.steve/worklog_hook.py && curl -fsSL https://raw.githubusercontent.com/west007-vante/cockpit-trinity/main/setup/install_worklog.py -o ~/.steve/install_worklog.py && python3 ~/.steve/install_worklog.py goggins
```

> ⚠️ **Reparou?** A ÚNICA diferença é a última palavra: Davi usa `rico`, Murilo usa `goggins`. Não troca, senão seu trabalho aparece no nome do outro.

### Passo 3 — Confere se deu certo
Tem que aparecer no Terminal:
```
✅ Worklog instalado.
```
Se apareceu isso, **deu certo.** ✅

### Passo 4 — Fecha e abre o Claude Code
Fecha o Claude Code **completamente** (`Cmd + Q`) e abre de novo. (Sem isso não ativa.)

### Passo 5 — Testa (opcional, mas legal)
Pede pro Claude Code criar qualquer arquivinho de teste. Depois abra o cockpit:
**https://west007-vante.github.io/cockpit-trinity/** → aba **Cockpit** → seção **"Trabalho da equipe"**. Seu nome vai estar lá com o que você fez. 🎉

---

## 🆘 Se der erro

**Apareceu "command not found: python3"?**
Roda isto uma vez e tenta de novo: `xcode-select --install` (instala as ferramentas do Mac).

**Qualquer outra coisa estranha?** Tira print da tela do Terminal e me manda. Não tem como quebrar nada — no pior caso a gente desfaz em 10 segundos.

---

**Resumão:** cola 1 comando → vê "✅ Worklog instalado" → fecha e abre o Claude Code → pronto pra sempre. 🚀
