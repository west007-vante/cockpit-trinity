# 🔗 Lado de lá — o sistema do Davi lendo as sessões do Pyerri

Dois universos ligados por uma ponte. Os dados de trabalho do Pyerri **não moram
aqui** — moram no banco dele (Steve). Este lado só atravessa, com um token que
ele emite e pode revogar a qualquer momento.

## Como funciona

```
 Claude Code do Pyerri
        │  hook grava título + resumo  ──────────┐
        │  sincronizar.py sobe o markdown        │
        │         ↑ passa pela FAXINA            ▼
        │                                 banco Steve (schema trinity)
        │                                        │
        │                          trinity_buscar / trinity_abrir
        │                            (exigem PONTE_TOKEN)
        │                                        │
        └────────────────────────────────►  app do Davi (Vercel)
                                                 │
                                          espelho opcional em
                                          ponte.sessoes_pyerri
```

**Nada atravessa sem faxina.** Antes de sair da máquina do Pyerri, cada transcrição
passa por um filtro que mascara chave, token, senha e string de conexão. O que chega
aqui vem com `‹CHAVE-SUPABASE mascarada›` no lugar do segredo, e o campo `mascarados`
diz quantos foram tirados.

## Instalar

**1.** Copie [`ponte.ts`](ponte.ts) para o projeto (ex.: `lib/ponte.ts`).

**2.** Na Vercel → *Settings → Environment Variables*, adicione as três:

| Variável | Valor |
|---|---|
| `STEVE_URL` | `https://rlrxeegnwjsmxwzoytiz.supabase.co` |
| `STEVE_ANON` | a anon key do banco Steve — o Pyerri passa |
| `PONTE_TOKEN` | o token `pnt_…` — **o Pyerri passa em privado** |

> ⚠️ **Nunca** use `NEXT_PUBLIC_` nessas. O `PONTE_TOKEN` no navegador daria a
> qualquer visitante acesso às sessões do Pyerri. Só server-side.

**3.** Use:

```ts
import { buscarSessoes, abrirSessao } from '@/lib/ponte';

// app/api/sessoes/route.ts
export async function GET(req: Request) {
  const termo = new URL(req.url).searchParams.get('q') ?? undefined;
  return Response.json(await buscarSessoes(termo, 20));
}

// app/api/sessoes/[id]/route.ts
export async function GET(_: Request, { params }: { params: { id: string } }) {
  const sessao = await abrirSessao(params.id);
  if (!sessao) return new Response('não achei', { status: 404 });
  return Response.json(sessao);           // sessao.markdown = a sessão inteira
}
```

## O que já está pronto no seu banco

Schema **`ponte`** (criado e trancado):

| Objeto | Pra quê |
|---|---|
| `ponte.config` | guarda `steve_url`, `steve_anon`, `ponte_token`. **Sem acesso** pra `anon` nem `authenticated` — só o service role lê |
| `ponte.sessoes_pyerri` | espelho local do que já foi puxado, com busca full-text em português. Leitura só pra usuário logado |

O espelho é opcional — `abrirSessao()` sozinho já resolve. Use `espelhar()` se quiser
cache local e busca dentro do seu próprio banco.

## Limites da travessia

- O token está amarrado a **ver só as sessões do `steve`** (o Pyerri). Não enxerga as suas.
- **Só sessão de trabalho aparece.** Conversa pura — pergunta e resposta — nunca sobe.
- Cada `buscar` e cada `abrir` fica registrado em `trinity.acessos`, do lado dele.
- Se o Pyerri rodar `trinity_revogar_ponte('sistema-davi')`, a porta fecha na hora.
