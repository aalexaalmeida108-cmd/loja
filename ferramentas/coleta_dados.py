#!/usr/bin/env python3
"""Coleta dados REAIS de cada link (titulo + imagem principal validada),
salva produtos.json e reconstrói o grid da vitrine."""
import glob
import io
import json
import os
import re
import sys
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "img")
PEDIDOS_DIR = os.path.join(ROOT, "pedidos")

BAD_WORDS = ("logo", "icon", "flag", "avatar", "sprite", "user-", "pixel")
MIN_BYTES = 8000
MIN_DIM = 200

OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)"
)
OGT_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)"
)
TW_RE = re.compile(
    r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+content=[\"']([^\"']+)"
)
CDN_RE = re.compile(
    r"https://[a-z0-9.-]*img\.susercontent\.com/[A-Za-z0-9._/-]{8,}"
)
TITLE_TAG_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)


def http_get(url, timeout=40):
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(), r.headers.get("content-type", "")


def fetch_via_jina(url):
    req = Request("https://r.jina.ai/" + url, headers={"User-Agent": UA})
    with urlopen(req, timeout=120) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_title(t):
    t = re.sub(r"\s*\|.*$", "", t or "")
    t = re.sub(r"[\"']", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:90]


def extract_title(txt):
    m = OGT_RE.search(txt)
    if m:
        return clean_title(m.group(1))
    m = TITLE_TAG_RE.search(txt)
    if m:
        return clean_title(m.group(1))
    return ""


def jsonld_products(txt):
    out = []
    for m in re.finditer(r"<script[^>]+ld\+json[^>]*>(.*?)</script>", txt, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        stack = d if isinstance(d, list) else [d]
        for item in stack:
            if isinstance(item, dict):
                if str(item.get("@type", "")).lower() == "product":
                    out.append(item)
                for g in item.get("@graph", []) if isinstance(item.get("@graph"), list) else []:
                    if isinstance(g, dict) and str(g.get("@type", "")).lower() == "product":
                        out.append(g)
    return out


def upgrade_shopee_url(u):
    u = u.replace("_tn.", ".")
    u = re.sub(r"\.(webp|jpg|jpeg|png)\?.*$", r".\1", u)
    return u


def candidate_images(txt, base):
    cands = []
    for jd in jsonld_products(txt):
        img = jd.get("image")
        if isinstance(img, str):
            cands.append(("jsonld", urljoin(base, img)))
        elif isinstance(img, list):
            for x in img[:3]:
                if isinstance(x, str):
                    cands.append(("jsonld", urljoin(base, x)))
    m = OG_RE.search(txt) or TW_RE.search(txt)
    if m:
        cands.append(("og", urljoin(base, m.group(1))))
    seen = set()
    for m in CDN_RE.finditer(txt):
        u = upgrade_shopee_url(m.group(0))
        low = u.lower()
        if any(b in low for b in BAD_WORDS):
            continue
        if u not in seen:
            seen.add(u)
            cands.append(("cdn", u))
    ranked = []
    for src, u in cands:
        score = {"jsonld": 3, "og": 2, "cdn": 1}[src]
        ranked.append((score, u))
    ranked.sort(key=lambda x: -x[0])
    final = []
    seen2 = set()
    for _, u in ranked:
        if u.startswith("http") and u not in seen2:
            seen2.add(u)
            final.append(u)
    return final


def image_ok(data):
    if len(data) < MIN_BYTES:
        return False
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        return w >= MIN_DIM and h >= MIN_DIM
    except Exception:
        return False


def url_key(url):
    m = re.search(r"shopee\.com\.br/([A-Za-z0-9._-]{6,})", url)
    if m:
        return m.group(1)
    u = re.sub(r"[?#].*$", "", url)
    return u.rstrip("/").split("/")[-1] or u


def get_link_data(url):
    """Retorna dict {title, img_path} ou None. Tenta direto, depois jina."""
    final = url
    try:
        final, data, ctype = http_get(url)
    except Exception as exc:
        print(f"  abertura falhou: {exc}")
        final = None
    fontes = []
    if final:
        fontes.append(data.decode("utf-8", errors="replace"))
    fontes.append(None)  # marcador para tentar jina depois

    title = ""
    for txt in fontes:
        if txt is None:
            try:
                txt = fetch_via_jina(final or url)
            except Exception as je:
                print(f"  jina falhou: {je}")
                continue
        if not title:
            title = extract_title(txt)
        for u in candidate_images(txt, final or url):
            try:
                _, data, ctype2 = http_get(u)
            except Exception:
                continue
            if image_ok(data):
                ext = ".jpg"
                low = u.lower()
                if ".png" in low or "png" in ctype2:
                    ext = ".png"
                elif ".webp" in low or "webp" in ctype2:
                    ext = ".webp"
                fp = os.path.join(IMG_DIR, f"tmp{ext}")
                with open(fp, "wb") as f:
                    f.write(data)
                return {"title": title, "img_path": fp}
            print(f"  imagem rejeitada ({len(data)}b): {u[:80]}")
    return None


# ---------- reconstrucao da vitrine ----------

DIV_RE = re.compile(r"<div\b|</div>")


def block_span(html, start):
    depth = 0
    i = start
    while i < len(html):
        m = DIV_RE.search(html, i)
        if not m:
            return len(html)
        if m.group(0) == "</div>":
            depth -= 1
            if depth == 0:
                return m.end()
        else:
            depth += 1
        i = m.end()
    return len(html)


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


BADGES = [
    ("badge-hot", "Destaque"),
    ("badge-toprated", "Mais Vendido"),
    ("badge-shipping", "Frete Grátis"),
]


def make_card(num, rel, url, titulo):
    bcls, btxt = BADGES[(num - 1) % len(BADGES)]
    t = esc(titulo or f"Produto Oferta #{num:02d}")
    return (
        f'\n      <!-- Produto {num:02d}: {url} -->\n'
        f'      <div class="card">\n'
        f'        <div class="card-img-wrapper">\n'
        f'          <img class="card-img" src="{rel}" alt="{t}">\n'
        f'          <span class="card-badge {bcls}">{btxt}</span>\n'
        f"        </div>\n"
        f'        <div class="card-body">\n'
        f'          <div class="card-cat">Eletroeletrônicos #{num:02d}</div>\n'
        f'          <h3 class="card-title">{t}</h3>\n'
        f'          <p class="card-desc">Oferta especial direto na Shopee, '
        f'aproveite enquanto durar o estoque!</p>\n'
        f'          <a href="{url}" target="_blank" rel="noopener noreferrer" '
        f'class="btn-buy">Ver Oferta na Shopee 🛒</a>\n'
        f"        </div>\n"
        f"      </div>"
    )


def rebuild(results):
    p = os.path.join(ROOT, "index.html")
    html = open(p, encoding="utf-8").read()
    g0 = html.find('<div class="grid" id="productGrid">')
    if g0 < 0:
        print("grid nao encontrado!")
        return
    g_end = block_span(html, g0)
    body_start = html.find(">", g0) + 1

    cards = []
    for n, r in enumerate(results, 1):
        rel = "img/" + os.path.basename(r["img_path"])
        cards.append(make_card(n, rel, r["url"], r["title"]))

    # limpa imagens antigas nao usadas
    usadas = {os.path.basename(r["img_path"]) for r in results}
    for f in glob.glob(os.path.join(IMG_DIR, "*")):
        if os.path.basename(f) not in usadas:
            os.remove(f)

    css = (
        "    .card-img {\n"
        "      position: absolute;\n"
        "      inset: 0;\n"
        "      width: 100%;\n"
        "      height: 100%;\n"
        "      object-fit: cover;\n"
        "    }\n"
    )
    new_html = html[:body_start] + "\n" + "\n".join(cards) + "\n" + html[g_end:]
    if ".card-img {" not in new_html:
        new_html = new_html.replace("</style>", css + "  </style>", 1)
    with open(p, "w", encoding="utf-8") as f:
        f.write(new_html)
    print(f"grid reconstruido com {len(cards)} cards")


def main():
    links = []
    if os.path.isdir(PEDIDOS_DIR):
        for fn in sorted(os.listdir(PEDIDOS_DIR)):
            p = os.path.join(PEDIDOS_DIR, fn)
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    for ln in f:
                        ln = ln.strip()
                        if ln.startswith("http") and ln not in links:
                            links.append(ln)

    print(f"processando {len(links)} link(s)...")
    os.makedirs(IMG_DIR, exist_ok=True)
    results = []
    for i, url in enumerate(links, 1):
        key = url_key(url)
        print(f"[{i}/{len(links)}] {key}")
        d = get_link_data(url)
        if not d:
            print("  SEM DADOS - pulando")
            continue
        final_name = f"produto_{i:02d}{os.path.splitext(d['img_path'])[1]}"
        final_fp = os.path.join(IMG_DIR, final_name)
        os.replace(d["img_path"], final_fp)
        results.append(
            {"num": i, "key": key, "url": url, "title": d["title"], "img_path": final_fp}
        )
        print(f"  OK: {d['title']!r}")

    with open(os.path.join(ROOT, "produtos.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    if results:
        rebuild(results)

    if os.path.isdir(PEDIDOS_DIR):
        for fn in os.listdir(PEDIDOS_DIR):
            os.remove(os.path.join(PEDIDOS_DIR, fn))
    print(f"fim: {len(results)} produto(s) coletado(s)")


if __name__ == "__main__":
    main()
