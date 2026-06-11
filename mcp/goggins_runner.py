#!/usr/bin/env python3
"""Goggins Runner — roda na M1 do Murilo (Claude Code CLI como cérebro opcional).

O elo REAL da esteira de CRIAÇÃO:
  1) puxa as tarefas de stage='criacao' atribuídas ao Goggins (get_tasks)
  2) pra cada oferta, gera N criativos ÚNICOS via o roteador (Cloudflare FLUX, custo R$0)
  3) salva cada criativo no Cockpit (save_creative) — Rico pega depois
  4) conclui a tarefa (report_progress done) → o trigger NASCE a tarefa do Steve sozinho

Usa o mesmo .env do conector (TRINITY_* + CF_ACCOUNT_ID + CF_API_TOKEN).
  python3 goggins_runner.py            # roda 1 vez
  python3 goggins_runner.py --loop     # fica de plantão (a cada 30s)
"""
import os, sys, time
import trinity_agent as ag
import creative_router as cr

N = int(os.environ.get("CREATIVES_PER_OFFER", "200"))

def run_once():
    q = ag.get_tasks()
    tasks = [t for t in q.get("tasks", []) if t.get("stage") == "criacao" and t.get("offer_id")]
    if not tasks:
        return 0
    for t in tasks:
        oid = t["offer_id"]
        offer = ag._req("GET", "cockpit_offers", params=f"?id=eq.{oid}&select=title,niche")
        title = (offer[0]["title"] if offer else "Oferta")
        ag.report_progress(t["id"], 5, "doing")
        ag.log_activity("create", f"Gerando {N} criativos únicos pra '{title}'…")
        made = 0
        for i in range(N):
            c = cr.generate(title, f"{title} — {cr.unique_variant(i)['angle']}", i, mode="test")
            if c.get("url"):
                ag.save_creative(oid, c["url"], c["kind"], c["headline"], c["angle"], c["source"], c["variant_key"])
                made += 1
                if made % 25 == 0:
                    ag.report_progress(t["id"], min(99, int(made / N * 100)), "doing")
        ag.report_progress(t["id"], 100, "done")   # ← dispara o handoff pro Steve
        ag.log_activity("win", f"{made} criativos únicos prontos pra '{title}' → entregue pro Steve")
    return len(tasks)

if __name__ == "__main__":
    ag.register()
    if "--loop" in sys.argv:
        print("[goggins] de plantão — puxando tarefas de criação a cada 30s", file=sys.stderr)
        while True:
            try:
                n = run_once()
                if n:
                    print(f"[goggins] processou {n} oferta(s)", file=sys.stderr)
            except Exception as e:
                print("[goggins] erro:", e, file=sys.stderr)
            time.sleep(30)
    else:
        print(f"[goggins] processou {run_once()} oferta(s)")
