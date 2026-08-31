# Ligar a Google Agenda

**Tempo:** ~10 minutos, uma vez só.
**Custo:** zero.
**Por que precisa disso:** o Trello grátis não tem calendário de verdade — o
Planner é só leitura. O evento com alarme no seu celular vem da Google Agenda.

> **Eu não faço nenhum destes passos por você.** Login e autorização são atos do
> dono da conta. Eu preparei o script; você clica.

---

## Passo 1 — criar o projeto

1. Abra **console.cloud.google.com**
2. No topo, no seletor de projeto → **Novo projeto**
3. Nome: `O QUADRO` → **Criar**
4. Espere e **selecione o projeto novo** no seletor (erro clássico: criar e continuar no projeto antigo)

## Passo 2 — ligar a API da Agenda

1. Menu → **APIs e serviços** → **Biblioteca**
2. Busque `Google Calendar API` → **Ativar**

## Passo 3 — a tela de consentimento

1. **APIs e serviços** → **Tela de permissão OAuth**
2. Tipo: **Externo** → **Criar**
3. Preencha só o obrigatório:
   - Nome do app: `O QUADRO`
   - E-mail de suporte e e-mail do desenvolvedor: **o seu**
4. Salvar e continuar → em **Escopos**, não adicione nada → Salvar
5. Em **Usuários de teste** → **Adicionar** → **o seu e-mail**
   > ⚠️ Este passo é o que mais trava gente. Sem seu e-mail aqui, o Google
   > recusa a autorização com "app não verificado" e não deixa seguir.
6. Salvar

## Passo 4 — a credencial

1. **APIs e serviços** → **Credenciais** → **Criar credenciais** → **ID do cliente OAuth**
2. Tipo de aplicativo: **App para computador** ← precisa ser esse
3. Nome: `robô do quadro` → **Criar**
4. Na janela que abre: **Fazer download do JSON**

## Passo 5 — guardar o arquivo

```bash
mv ~/Downloads/client_secret_*.json ~/.steve/gcal_client.json && chmod 600 ~/.steve/gcal_client.json
```

## Passo 6 — autorizar

```bash
python3 ~/trinity/trello/gcal.py --conectar
```

Abre o navegador. **Confira na tela: tem que pedir só acesso a eventos de agenda.**
Se pedir e-mail ou contatos, cancele e me chame — não é pra pedir isso.

Vai aparecer um aviso de "app não verificado" (é seu app, feito agora):
**Avançado** → **Acessar O QUADRO (não seguro)**.

## Passo 7 — provar

```bash
python3 ~/trinity/trello/gcal.py
```

Lista suas agendas. Depois:

```bash
python3 ~/trinity/trello/gcal.py --teste
```

Cria um evento de teste daqui a 1h. **Confira no celular** — é a prova real de
que o alarme chega onde interessa. Depois apague pelo próprio celular.

---

## Escolher outra agenda

Por padrão vai na sua agenda principal. Pra mandar pra uma agenda separada
(recomendado — deixa filtrar e ocultar sem sujar a sua):

1. Crie a agenda no Google Agenda (Configurações → Adicionar agenda)
2. `python3 ~/trinity/trello/gcal.py` para ver o id dela
3. Acrescente em `~/.steve/gcal.env`:

```
GCAL_AGENDA=o_id_que_apareceu@group.calendar.google.com
```

---

## Se der problema

| Erro | O que é | Como resolve |
|---|---|---|
| `não achei ~/.steve/gcal_client.json` | passo 5 não foi feito | refaça o passo 5 |
| `não tem client_id/client_secret` | baixou o JSON errado | tem que ser **App para computador** |
| `o Google não mandou refresh_token` | esta conta já autorizou antes | revogue em **myaccount.google.com/permissions** e rode de novo |
| "app bloqueado" / "não verificado" sem opção de avançar | seu e-mail não está em Usuários de teste | passo 3, item 5 |
| `recusou renovar o acesso` | autorização revogada | `python3 gcal.py --conectar` de novo |

---

## Plano B — sem Google Cloud

Se isso te irritar, dá pra usar o Calendário do próprio Mac: você adiciona sua
conta Google em **Ajustes do Sistema → Contas de Internet**, e o robô cria o
evento por AppleScript. Sem nuvem, sem OAuth.

**O que se perde:** só funciona com o Mac ligado, a sincronização leva alguns
minutos, e o lado do Davi precisaria de um caminho próprio.

Me fale se quiser esse caminho que eu escrevo.

---

## Cortar o acesso

**myaccount.google.com/permissions** → O QUADRO → **Remover acesso**.
Na hora, sem mexer em código.
