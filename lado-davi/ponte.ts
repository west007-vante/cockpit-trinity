/* ─────────────────────────────────────────────────────────────────────
   PONTE — o sistema do Davi lendo as sessões de trabalho do Pyerri.

   Dois universos: os dados do Pyerri moram no banco dele (Steve). Aqui a
   gente só ATRAVESSA, com um token que ele pode revogar quando quiser.

   ⚠️  SÓ NO SERVIDOR. O PONTE_TOKEN nunca pode ir pro navegador — nada de
   NEXT_PUBLIC_. Use em route handlers, server actions ou server components.

   Variáveis de ambiente (na Vercel → Settings → Environment Variables):
     STEVE_URL    = https://rlrxeegnwjsmxwzoytiz.supabase.co
     STEVE_ANON   = <a anon key do banco Steve>
     PONTE_TOKEN  = <o token pnt_… que o Pyerri emitiu pra você>
   ───────────────────────────────────────────────────────────────────── */

const URL_STEVE = process.env.STEVE_URL!;
const ANON = process.env.STEVE_ANON!;
const TOKEN = process.env.PONTE_TOKEN!;

export type SessaoResumo = {
  session_id: string;
  dono: string;
  titulo: string;
  resumo: string | null;
  bytes: number | null;
  mascarados: number | null;
  terminou_em: string;
  tem_documento: boolean;
};

export type SessaoCompleta = {
  session_id: string;
  dono: string;
  titulo: string;
  markdown: string;
  mascarados: number;
  terminou_em: string;
};

async function chamar<T>(funcao: string, corpo: Record<string, unknown>): Promise<T> {
  if (!URL_STEVE || !ANON || !TOKEN) {
    throw new Error('ponte: faltam STEVE_URL / STEVE_ANON / PONTE_TOKEN no ambiente');
  }
  const r = await fetch(`${URL_STEVE}/rest/v1/rpc/${funcao}`, {
    method: 'POST',
    headers: {
      apikey: ANON,
      Authorization: `Bearer ${ANON}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ p_token: TOKEN, ...corpo }),
    cache: 'no-store',
  });
  if (!r.ok) {
    const detalhe = await r.text();
    throw new Error(`ponte/${funcao} ${r.status}: ${detalhe.slice(0, 200)}`);
  }
  return r.json() as Promise<T>;
}

/** Lista as sessões de trabalho do Pyerri. `termo` busca no título e no conteúdo. */
export function buscarSessoes(termo?: string, limite = 20) {
  return chamar<SessaoResumo[]>('trinity_buscar', {
    p_termo: termo ?? null,
    p_limite: limite,
  });
}

/** Traz uma sessão inteira em markdown — já sem chave, senha ou token. */
export async function abrirSessao(sessionId: string) {
  const linhas = await chamar<SessaoCompleta[]>('trinity_abrir', {
    p_session_id: sessionId,
  });
  return linhas[0] ?? null;
}

/* ─────────────────────────────────────────────────────────────────────
   Espelho local (opcional): guarda no seu banco o que já foi puxado, pra
   não bater na ponte toda vez. A fonte da verdade continua sendo o Steve.
   Precisa do client Supabase com a SERVICE key — server-side, sempre.
   ───────────────────────────────────────────────────────────────────── */
export async function espelhar(
  supabaseAdmin: { schema: (s: string) => any },
  termo?: string,
  limite = 20,
) {
  const resumos = await buscarSessoes(termo, limite);
  const completas = await Promise.all(
    resumos.filter((s) => s.tem_documento).map((s) => abrirSessao(s.session_id)),
  );

  const linhas = completas.filter(Boolean).map((s) => ({
    session_id: s!.session_id,
    dono: s!.dono,
    titulo: s!.titulo,
    resumo: resumos.find((r) => r.session_id === s!.session_id)?.resumo ?? null,
    markdown: s!.markdown,
    mascarados: s!.mascarados,
    terminou_em: s!.terminou_em,
    puxado_em: new Date().toISOString(),
  }));

  if (linhas.length) {
    const { error } = await supabaseAdmin
      .schema('ponte')
      .from('sessoes_pyerri')
      .upsert(linhas, { onConflict: 'session_id' });
    if (error) throw new Error(`ponte/espelho: ${error.message}`);
  }
  return linhas.length;
}
