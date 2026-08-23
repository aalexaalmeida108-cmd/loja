#!/usr/bin/env python3
"""Coleta dados REAIS de cada link Shopee.
Estrategias em cascata: HTML direto -> API v4/v2 -> Playwright -> Jina."""
import glob
import io
import json
import os
import re
import subprocess
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "img")
PEDIDOS_DIR = os.path.join(ROOT, "pedidos")

BAD_WORDS = ("logo", "icon", "flag", "avatar", "sprite", "pixel", "-banner")
MIN_BYTES = 8000
MIN_DIM = 200

OGT_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)"
)
TITLE_TAG_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
CDN_ANY_RE = re.compile(
    r"https://(?:cf\.shopee\.com\.br|down-[a-z-]*\.img\.susercontent\.com|[a-z0-9.-]*img\.susercontent\.com)/file/[A-Za-z0-9._-]{10,}"
)


def http_get(url, timeout=40, extra=None):
    h = {"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    if extra:
        h.update(extra)
    req = Request(url, headers=h)
    with urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(), r.headers.get("content-type", "")


def clean_title(t):
    t = re.sub(r"\s*\|.*$", "", t or "")
    t = re.sub(r"[\"']", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:90]


def image_ok(data):
    if len(data) < MIN_BYTES:
        return False
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.verify()
        im = Image.open(io.BytesIO(data))
        w, h = im.size
        return w >= MIN_DIM and h >= MIN_DIM
    except Exception:
        return False


def upgrade_shopee_url(u):
    u = u.replace("_tn.", ".")
    u = re.sub(r"\.(webp|jpg|jpeg|png)\?.*$", r".\1", u)
    return u


def pick_valid(candidates, tag=""):
    for u in candidates:
        if not u or not u.startswith("http"):
            continue
        low = u.lower()
        if any(b in low for b in BAD_WORDS):
            continue
        u2 = upgrade_shopee_url(u)
        try:
            _, data, ctype2 = http_get(u2, timeout=25)
        except Exception:
            try:
                _, data, ctype2 = http_get(u, timeout=25)
                u2 = u
            except Exception:
                continue
        if image_ok(data):
            ext = ".jpg"
            low = u2.lower()
            if ".png" in low or "png" in ctype2:
                ext = ".png"
            elif ".webp" in low or "webp" in ctype2:
                ext = ".webp"
            fp = os.path.join(IMG_DIR, f"cand{ext}")
            with open(fp, "wb") as f:
                f.write(data)
            print(f"  imagem ok ({len(data)}b) [{tag}]")
            return fp
        print(f"  rejeitada ({len(data)}b): {u2[:75]}")
    return None


# ---------- estrategia 1: html direto ----------

def via_html(url):
    final, data, ctype = http_get(url)
    if "image/" in ctype and image_ok(data):
        ext = ".jpg"
        if "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        fp = os.path.join(IMG_DIR, f"cand{ext}")
        with open(fp, "wb") as f:
            f.write(data)
        return "", fp
    txt = data.decode("utf-8", errors="replace")
    title = ""
    m = OGT_RE.search(txt) or TITLE_TAG_RE.search(txt)
    if m:
        title = clean_title(m.group(1))
    cands = []
    seen = set()
    for m in CDN_ANY_RE.finditer(txt):
        u = upgrade_shopee_url(m.group(0))
        if u not in seen:
            seen.add(u)
            cands.append(u)
    # prioriza imagens grandes conhecidas do padrao shopee
    cands.sort(key=lambda u: ("_tn" in u.lower(), len(u)))
    fp = pick_valid(cands[:6], "html")
    return title, fp


# ---------- estrategia 2: api oficial ----------

def ids_from_url(u):
    m = re.search(r"-i\.(\d+)\.(\d+)", u)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"/product/(\d+)/(\d+)", u)
    if m:
        return m.group(1), m.group(2)
    return None


def via_api(final_url):
    ids = ids_from_url(final_url)
    if not ids:
        print("  sem ids na url")
        return None, None
    shop, item = ids
    endpoints = [
        f"https://shopee.com.br/api/v4/pdp/get_pc?item_id={item}&shop_id={shop}&detail_level=0",
        f"https://mall.shopee.com.br/api/v2/item/get?itemid={item}&shopid={shop}",
    ]
    for ep in endpoints:
        try:
            _, raw, _ = http_get(
                ep,
                timeout=30,
                extra={
                    "Referer": "https://shopee.com.br/",
                    "X-API-SOURCE": "pc",
                    "Accept": "application/json",
                },
            )
            d = json.loads(raw)
            itemd = d.get("item") or (d.get("data") or {}).get("item")
            if not itemd:
                continue
            name = clean_title(itemd.get("name", ""))
            imgs = []
            for im in itemd.get("images", []):
                u = im if str(im).startswith("http") else (
                    "https://cf.shopee.com.br/file/" + str(im)
                )
                imgs.append(u)
            fp = pick_valid(imgs[:5], "api")
            if fp:
                return name, fp
        except Exception as e:
            print(f"  api falhou ({ep[:55]}): {str(e)[:80]}")
    return None, None


# ---------- estrategia 3: playwright ----------

def via_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"  playwright indisponivel: {e}")
        return None, None
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
            )
            pg = b.new_page(user_agent=UA, viewport={"width": 1280, "height": 900})
            pg.goto(url, timeout=60000, wait_until="domcontentloaded")

            def _smart_title():
                c = pg.content()
                m = OGT_RE.search(c)
                if m:
                    t = clean_title(m.group(1))
                    if t and t.lower() != "shopee brasil":
                        return t
                try:
                    for jd in jsonld_products(c):
                        nm = jd.get("name")
                        if nm:
                            t = clean_title(str(nm))
                            if t and t.lower() != "shopee brasil":
                                return t
                except Exception:
                    pass
                return ""

            title = ""
            for _ in range(6):
                title = _smart_title()
                if title:
                    break
                try:
                    pg.mouse.wheel(0, 1500)
                except Exception:
                    pass
                pg.wait_for_timeout(3000)
            srcs = pg.eval_on_selector_all("img", "els => els.map(e => e.src)")
            content = pg.content()
            if not title:
                m_og = OGT_RE.search(content)
                if m_og:
                    title = clean_title(m_og.group(1))
                else:
                    title = clean_title(pg.title() or "")
            b.close()
    except Exception as e:
        print(f"  playwright erro: {str(e)[:100]}")
        return None, None

    cands = []
    seen = set()
    for u in srcs or []:
        if "susercontent" in u or "cf.shopee" in u:
            u = upgrade_shopee_url(u.split("?")[0])
            if u not in seen:
                seen.add(u)
                cands.append(u)
    # procura no estado embutido tambem
    for m in CDN_ANY_RE.finditer(content):
        u = upgrade_shopee_url(m.group(0))
        if u not in seen:
            seen.add(u)
            cands.append(u)
    if not title:
        m = OGT_RE.search(content)
        if m:
            title = clean_title(m.group(1))
    fp = pick_valid(cands[:10], "playwright")
    return title, fp


# ---------- estrategia 4: jina ----------

def via_jina(url):
    try:
        req = Request("https://r.jina.ai/" + url, headers={"User-Agent": UA})
        txt = urlopen(req, timeout=120).read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  jina falhou: {str(e)[:80]}")
        return None, None
    title = ""
    m = OGT_RE.search(txt) or TITLE_TAG_RE.search(txt)
    if m:
        title = clean_title(m.group(1))
    cands = []
    seen = set()
    for m in CDN_ANY_RE.finditer(txt):
        u = upgrade_shopee_url(m.group(0))
        if u not in seen:
            seen.add(u)
            cands.append(u)
    fp = pick_valid(cands[:6], "jina")
    return title, fp


def get_link_data(url):
    try:
        final, _, _ = http_get(url, timeout=30)
    except Exception:
        final = url
    print("  [1] api shopee...")
    t, fp = via_api(final)
    if fp:
        return t, fp
    print("  [2] playwright...")
    t2, fp = via_playwright(final or url)
    if fp:
        return t2 or t, fp
    print("  [3] html direto...")
    t3, fp = via_html(url)
    if fp:
        return t3 or t2 or t, fp
    print("  [4] jina...")
    t4, fp = via_jina(final or url)
    if fp:
        return t4 or t3 or t2 or t, fp
    return None, None


def fetch_name_only(final_url):
    ids = ids_from_url(final_url)
    if not ids:
        return ""
    shop, item = ids
    for ep in (
        f"https://shopee.com.br/api/v4/pdp/get_pc?item_id={item}&shop_id={shop}&detail_level=0",
        f"https://mall.shopee.com.br/api/v2/item/get?itemid={item}&shopid={shop}",
    ):
        try:
            _, raw, _ = http_get(
                ep,
                timeout=30,
                extra={
                    "Referer": "https://shopee.com.br/",
                    "X-API-SOURCE": "pc",
                    "Accept": "application/json",
                },
            )
            d = json.loads(raw)
            itemd = d.get("item") or (d.get("data") or {}).get("item")
            if itemd and itemd.get("name"):
                return clean_title(itemd["name"])
        except Exception:
            pass
    return ""


def url_key(url):
    m = re.search(r"shopee\.com\.br/([A-Za-z0-9._-]{6,})", url)
    if m:
        return m.group(1)
    u = re.sub(r"[?#].*$", "", url)
    return u.rstrip("/").split("/")[-1] or u


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
        sys.exit(1)
    g_end = block_span(html, g0)
    body_start = html.find(">", g0) + 1

    cards = []
    for n, r in enumerate(results, 1):
        rel = "img/" + os.path.basename(r["img_path"])
        cards.append(make_card(n, rel, r["url"], r["title"]))

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

    EXPECTED = [
        "https://s.shopee.com.br/2qU05vxDvw",
        "https://s.shopee.com.br/6VNIShMSUA",
        "https://s.shopee.com.br/3B6qUbLLbJ",
        "https://s.shopee.com.br/5VUlGuPBuu",
        "https://s.shopee.com.br/3qMXHriOq2",
        "https://s.shopee.com.br/7psg3EOA6s",
        "https://s.shopee.com.br/6AkS4CyUsr",
        "https://s.shopee.com.br/50YUg5BTIB",
        "https://s.shopee.com.br/3qMXHxfuNF",
        "https://s.shopee.com.br/7VFpejijv3",
        "https://s.shopee.com.br/5ArusTHcJz",
        "https://s.shopee.com.br/2gAZttMC2F",
    ]
    alvos = []
    for u in EXPECTED:
        if u not in alvos:
            alvos.append(u)
    for u in links:
        if u not in alvos:
            alvos.append(u)

    def titulo_ruim(t):
        t = (t or "").strip()
        return len(t) < 8 or t.lower() == "shopee brasil"

    prev = {}
    pj = os.path.join(ROOT, "produtos.json")
    if os.path.exists(pj):
        try:
            for r in json.load(open(pj)):
                prev[url_key(r["url"])] = r
        except Exception:
            pass

    print(f"processando {len(alvos)} produto(s)...")
    os.makedirs(IMG_DIR, exist_ok=True)
    results = []
    for i, url in enumerate(alvos, 1):
        key = url_key(url)
        antigo = prev.get(key)
        tem_img = bool(antigo) and os.path.exists(str(antigo.get("img_path", "")))
        bom_titulo = bool(antigo) and not titulo_ruim(antigo.get("title"))
        if tem_img and bom_titulo:
            r = dict(antigo)
            r["num"] = i
            results.append(r)
            continue

        falta_soh_titulo = tem_img and not bom_titulo
        print(f"[{i}/{len(alvos)}] {key}" + (" (so titulo)" if falta_soh_titulo else ""))

        title = ""
        if falta_soh_titulo:
            try:
                fin, _, _ = http_get(url, timeout=30)
            except Exception:
                fin = url
            title = fetch_name_only(fin)
            if not title:
                t2, _ = via_playwright(fin or url)
                title = t2 or ""
            if titulo_ruim(title):
                print("  titulo nao recuperado, mantendo anterior")
                title = antigo.get("title", "")
            r = dict(antigo)
            r["num"] = i
            r["title"] = title
            results.append(r)
            print(f"  titulo: {title!r}")
            continue

        d = get_link_data(url)
        if not d or not d[1]:
            if antigo and tem_img:
                r = dict(antigo)
                r["num"] = i
                results.append(r)
                print("  mantendo imagem anterior")
                continue
            print("  SEM DADOS - pulando")
            continue
        title, fp = d
        if titulo_ruim(title):
            fin = url
            title2 = fetch_name_only(fin)
            if not titulo_ruim(title2 or ""):
                title = title2
        final_name = f"produto_{i:02d}{os.path.splitext(fp)[1]}"
        final_fp = os.path.join(IMG_DIR, final_name)
        os.replace(fp, final_fp)
        results.append(
            {"num": i, "key": key, "url": url, "title": title, "img_path": final_fp}
        )
        print(f"  OK: {title!r}")

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
