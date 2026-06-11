#!/usr/bin/env python3
"""Creative Router — gera criativos ÚNICOS em massa gastando o MÍNIMO.

Filosofia (Pyerri): cada criativo é único → testa 200/dia → mede engajamento×conversão
→ só o VENCEDOR é regerado em premium. Roteamento por custo:

  modo 'test'  (volume A/B):  FREE  → Cloudflare FLUX (grátis, real) → upload no storage
  modo 'scale' (vencedor):    PAGO  → Genspark nano-banana (texto-na-imagem) c/ orçamento

Env: TRINITY_URL, TRINITY_SERVICE_KEY, CF_ACCOUNT_ID, CF_API_TOKEN  (Higgsfield/Canva = slots).
CLI: python3 creative_router.py "Confeitaria Lucrativa" "Quanto cobrar no brigadeiro" 5
"""
import os, sys, json, time, base64, hashlib, subprocess, urllib.request
from urllib.parse import quote

TRINITY_URL = os.environ.get("TRINITY_URL", "").rstrip("/")
TRINITY_KEY = os.environ.get("TRINITY_SERVICE_KEY", "")
CF_ACC = os.environ.get("CF_ACCOUNT_ID", "")
CF_TOK = os.environ.get("CF_API_TOKEN", "")
GENSPARK_DAILY = float(os.environ.get("CREATIVE_GENSPARK_DAILY_USD", "2.50"))

# ── eixos de variação (NENHUM criativo é igual) ──
ANGLE = ['benefício direto', 'dor/problema', 'prova social', 'curiosidade', 'antes e depois', 'autoridade', 'urgência', 'storytelling']
LIGHT = ['golden hour', 'studio softbox', 'dramático contraste', 'natural suave', 'neon', 'flat lay', 'cinematográfico']
COMP  = ['close macro', 'regra dos terços', 'herói centralizado', 'diagonal', 'overhead', 'split-screen', 'simétrico']
MOOD  = ['premium', 'aspiracional', 'cru e autêntico', 'minimalista', 'vibrante', 'acolhedor']

def unique_variant(i):
    return {'angle': ANGLE[i % len(ANGLE)], 'light': LIGHT[(i * 3) % len(LIGHT)],
            'comp': COMP[(i * 5) % len(COMP)], 'mood': MOOD[(i * 7) % len(MOOD)]}

def build_prompt(offer_title, headline, v, with_text):
    p = (f"professional marketing creative for '{offer_title}', {v['comp']} composition, "
         f"{v['light']} lighting, {v['mood']} mood, angle: {v['angle']}, photorealistic, "
         f"high-end advertising, scroll-stopping, not AI-looking, 4k")
    if with_text and headline:
        p += f", bold editorial headline integrated: \"{headline}\""
    return p

# ── FONTE FREE: Cloudflare FLUX → upload no storage (a URL vira o criativo) ──
def gen_cloudflare(prompt):
    body = json.dumps({"prompt": prompt}).encode()
    r = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{CF_ACC}/ai/run/@cf/black-forest-labs/flux-1-schnell",
        data=body, method="POST")
    r.add_header("Authorization", f"Bearer {CF_TOK}"); r.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(r, timeout=50) as resp:
        d = json.loads(resp.read())
    img = (d.get("result") or {}).get("image")
    return base64.b64decode(img) if img else None

def upload_storage(img_bytes, path):
    r = urllib.request.Request(f"{TRINITY_URL}/storage/v1/object/creatives/{path}", data=img_bytes, method="POST")
    r.add_header("apikey", TRINITY_KEY); r.add_header("Authorization", f"Bearer {TRINITY_KEY}")
    r.add_header("Content-Type", "image/png")
    try:
        urllib.request.urlopen(r, timeout=25)
        return f"{TRINITY_URL}/storage/v1/object/public/creatives/{path}"
    except Exception as e:
        print(f"[router] upload falhou: {e}", file=sys.stderr); return None

def gen_free(prompt, i):
    b = gen_cloudflare(prompt)
    if not b:
        return None
    return upload_storage(b, f"c_{int(time.time())}_{i}.png")

# ── FONTE PAGA: Genspark nano-banana (gsk CLI, texto real na imagem) ──
COST = {"genspark": 0.05}
_spent = {"genspark": 0.0}
def gen_genspark(prompt, out):
    try:
        subprocess.run(["gsk", "img", "-m", "nano-banana-pro", "-o", out, prompt],
                       check=True, capture_output=True, timeout=420)
        return out if os.path.exists(out) else None
    except Exception:
        return None

def generate(offer_title, headline, i, mode="test", out_dir="/tmp/creatives"):
    v = unique_variant(i)
    seed = int(hashlib.md5(f"{offer_title}|{i}".encode()).hexdigest()[:8], 16)
    vk = f"{i}-{v['angle'][:4]}-{v['light'][:4]}-{seed}"
    if mode == "scale" and _spent["genspark"] + COST["genspark"] <= GENSPARK_DAILY:
        os.makedirs(out_dir, exist_ok=True)
        path = gen_genspark(build_prompt(offer_title, headline, v, True), f"{out_dir}/c{i}.png")
        if path:
            url = upload_storage(open(path, "rb").read(), f"win_{int(time.time())}_{i}.png")
            _spent["genspark"] += COST["genspark"]
            return {"url": url, "source": "genspark", "kind": "image", "cost": COST["genspark"],
                    "angle": v['angle'], "headline": headline, "variant_key": vk}
    url = gen_free(build_prompt(offer_title, headline, v, False), i)
    return {"url": url, "source": "cloudflare", "kind": "image", "cost": 0.0,
            "angle": v['angle'], "headline": headline, "variant_key": vk}

def generate_batch(offer_title, headline, n=200, mode="test"):
    out = []
    for i in range(n):
        c = generate(offer_title, headline, i, mode)
        if c.get("url"):
            out.append(c)
    return out

if __name__ == "__main__":
    title = sys.argv[1] if len(sys.argv) > 1 else "Oferta Teste"
    head = sys.argv[2] if len(sys.argv) > 2 else "Headline de teste"
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    batch = generate_batch(title, head, n, mode="test")
    print(f"Gerados {len(batch)} criativos ÚNICOS (Cloudflare FLUX, custo R$0):")
    for c in batch:
        print(f"  [{c['source']}] {c['angle']:16s} {c['url']}")
    print(f"\nVariações distintas: {len(set(c['variant_key'] for c in batch))}/{len(batch)}")
