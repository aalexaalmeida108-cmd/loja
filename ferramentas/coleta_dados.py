#!/usr/bin/env python3
"""Gerencia a vitrine: registro dinamico em produtos.json + pedidos do bot.
Diretivas aceitas nos arquivos de pedido:
  https://...        -> adiciona produto novo
  -N https://...     -> substitui o produto numero N
  rem N              -> remove o produto numero N
Estrategias de coleta: HTML direto -> API -> Playwright -> Jina."""
import glob
import io
import json
import os
import re
import sys
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
REG_PATH = os.path.join(ROOT, "produtos.json")

BAD_WORDS = ("logo", "icon", "flag", "avatar", "sprite", "pixel", "-banner")
MIN_BYTES = 8000
MIN_DIM = 200

OGT_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)"
)
OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)"
)
TITLE_TAG_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
CDN_ANY_RE = re.compile(
    r"https://(?:cf\.shopee\.com\.br|down-[a-z-]*\.img\.susercontent\.com|[a-z0-9.-]*img\.susercontent\.com)/file/[A-Za-z0-9._/-]{10,}"
)


# ---------------- util ----------------

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


def url_key(url):
    m = re.search(r"shopee\.com\.br/([A-Za-z0-9._-]{6,})", url)
    if m:
        return m.group(1)
    u = re.sub(r"[?#].*$", "", url)
    return u.rstrip("/").split("/")[-1] or u


def titulo_ruim(t):
    t = (t or "").strip()
    return len(t) < 8 or t.lower() == "shopee brasil"


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


# ---------------- estrategias de coleta ----------------

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
            fp = os.path.join(IMG_DIR, "cand" + ext)
            with open(fp, "wb") as f:
                f.write(data)
            print(f"  imagem ok ({len(data)}b) [{tag}]")
            return fp
        print(f"  rejeitada ({len(data)}b): {u2[:75]}")
    return None


def ids_from_url(u):
    m = (
        re.search(r"/opaanlp/(\d+)/(\d+)", u)
        or re.search(r"-i\.(\d+)\.(\d+)", u)
        or re.search(r"/product/(\d+)/(\d+)", u)
    )
    if m:
        return m.group(1), m.group(2)
    return None


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
                g = item.get("@graph")
                if isinstance(g, list):
                    for gi in g:
                        if isinstance(gi, dict) and str(gi.get("@type", "")).lower() == "product":
                            out.append(gi)
    return out


def via_html(url):
    final, data, ctype = http_get(url)
    if "image/" in ctype and image_ok(data):
        ext = ".jpg"
        if "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        fp = os.path.join(IMG_DIR, "cand" + ext)
        with open(fp, "wb") as f:
            f.write(data)
        return "", fp
    txt = data.decode("utf-8", errors="replace")
    title = ""
    m = OGT_RE.search(txt) or TITLE_TAG_RE.search(txt)
    if m:
        title = clean_title(m.group(1))
    cands, seen = [], set()
    for m in CDN_ANY_RE.finditer(txt):
        u = upgrade_shopee_url(m.group(0))
        if u not in seen:
            seen.add(u)
            cands.append(u)
    cands.sort(key=lambda u: ("_tn" in u.lower(), len(u)))
    return title, pick_valid(cands[:6], "html")


def via_api(final_url):
    ids = ids_from_url(final_url)
    if not ids:
        print("  sem ids na url")
        return None, None
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
            if not itemd:
                continue
            name = clean_title(str(itemd.get("name", "")))
            imgs = []
            for im in itemd.get("images", []):
                imgs.append(
                    im if str(im).startswith("http")
                    else "https://cf.shopee.com.br/file/" + str(im)
                )
            fp = pick_valid(imgs[:5], "api")
            if fp:
                return name, fp
        except Exception as e:
            print(f"  api falhou ({ep[:55]}): {str(e)[:70]}")
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
                return clean_title(str(itemd["name"]))
        except Exception:
            pass
    return ""


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
            if not title:
                try:
                    dom_names = pg.eval_on_selector_all(
                        "h1, h2",
                        "els => els.map(e => (e.innerText || '').trim())"
                        ".filter(t => t && t.length >= 10 && t.length <= 130)",
                    )
                    if dom_names:
                        title = clean_title(max(dom_names, key=len))
                        print(f"  titulo do DOM: {title[:50]!r}")
                except Exception:
                    pass
            srcs = pg.eval_on_selector_all("img", "els => els.map(e => e.src)")
            content = pg.content()
            if not title:
                m = OGT_RE.search(content)
                if m:
                    title = clean_title(m.group(1))
                else:
                    title = clean_title(pg.title() or "")
            b.close()
    except Exception as e:
        print(f"  playwright erro: {str(e)[:100]}")
        return None, None

    cands, seen = [], set()
    for u in srcs or []:
        if "susercontent" in u or "cf.shopee" in u:
            u = upgrade_shopee_url(u.split("?")[0])
            if u not in seen:
                seen.add(u)
                cands.append(u)
    for m in CDN_ANY_RE.finditer(content):
        u = upgrade_shopee_url(m.group(0))
        if u not in seen:
            seen.add(u)
            cands.append(u)
    return title, pick_valid(cands[:10], "playwright")


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
    cands, seen = [], set()
    for m in CDN_ANY_RE.finditer(txt):
        u = upgrade_shopee_url(m.group(0))
        if u not in seen:
            seen.add(u)
            cands.append(u)
    return title, pick_valid(cands[:6], "jina")


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



CATS_KW = [
    ("Automotivo e Moto", [
        "capacete", "motocicleta", "moto ", "pro tork", "bateria automotiva",
        "bomba de ar", "pneu", "vonixx", "automotiv", "carro", "freio",
        "multimidia",
    ]),
    ("Ferramentas", [
        "furadeira", "parafusadeira", "chave de impacto", "kit ferrament",
        "martete", "nivel a laser", "nível a laser", "laser", "alicate",
        "serrote", "makita", "bosch", "dewalt", "jogo de chave",
        "torquimetro", "esmeril", "kit 6 ferramentas",
    ]),
    ("Mobilidade", [
        "bicicleta", "scooter", "patinete", "skate eletrico", "monociclo",
    ]),
    ("Games e Informatica", [
        "gabinete", "gamer", "teclado", "mouse", "headset", "monitor",
        "notebook", "placa de video", "memoria ram", "ssd ",
    ]),
    ("Eletronicos", [
        "fone", "smartwatch", "caixa de som", "power bank", "camera",
        "hub usb", "ring light", "smart tv", "projetor",
    ]),
]


def classifica_categoria(titulo: str) -> str:
    tl = (titulo or "").lower()
    for cat, kws in CATS_KW:
        for kw in kws:
            if kw in tl:
                return cat
    return "Outros"


def classifica_gemini(titulo: str) -> str:
    """Pede ao Gemini uma categoria curta quando as regras nao conhecem."""
    key = os.getenv("GEMINI_API_KEY", "")
    if not key or not titulo:
        return ""
    try:
        import requests as _rq
        r = _rq.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.5-flash:generateContent?key=" + key,
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    "Voce categoriza produtos de e-commerce. "
                                    "Responda APENAS com o nome de UMA categoria "
                                    "curta em português (1 a 3 palavras) para o "
                                    "produto abaixo. Nao explique.\n"
                                    "Produto: " + titulo
                                )
                            }
                        ]
                    }
                ],
                "generationConfig": {"temperature": 0.2},
            },
            timeout=30,
        )
        d = r.json()
        cat = (
            d["candidates"][0]["content"]["parts"][0]["text"]
            .strip()
            .strip(".")
            .splitlines()[0]
        )
        if 2 <= len(cat) <= 32 and "shopee" not in cat.lower():
            return cat.title()
    except Exception as e:
        print(f"  gemini classify falhou: {str(e)[:80]}")
    return ""


def classifica_final(titulo: str) -> str:
    c = classifica_categoria(titulo)
    if c != "Outros":
        return c
    g = classifica_gemini(titulo)
    return g if g else "Outros"


# ---------------- registro e pedidos ----------------

def carregar_registro():
    if os.path.exists(REG_PATH):
        try:
            return json.load(open(REG_PATH, encoding="utf-8"))
        except Exception:
            pass
    return []


def salvar_registro(reg):
    with open(REG_PATH, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=1)


def parse_pedidos():
    novos, trocas, rems = [], {}, []
    if os.path.isdir(PEDIDOS_DIR):
        for fn in sorted(os.listdir(PEDIDOS_DIR)):
            p = os.path.join(PEDIDOS_DIR, fn)
            if not os.path.isfile(p):
                continue
            with open(p, encoding="utf-8") as f:
                for ln in f:
                    ln = ln.strip()
                    if not ln:
                        continue
                    m = re.match(r"^-(\d+)\s+(https?://\S+)$", ln)
                    if m:
                        trocas[int(m.group(1))] = m.group(2)
                        continue
                    m = re.match(r"^rem\s+(\d+)$", ln, re.I)
                    if m:
                        rems.append(int(m.group(1)))
                        continue
                    if ln.startswith("http"):
                        novos.append(ln)
    return novos, trocas, rems


# ---------------- reconstrucao da pagina ----------------

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


def make_card(num, rel, url, titulo, categoria=""):
    bcls, btxt = BADGES[(num - 1) % len(BADGES)]
    t = esc(titulo or f"Produto #{num:02d}")
    dc = esc(categoria)
    return (
        f'\n      <!-- Produto {num:02d} [{dc}]: {url} -->\n'
        f'      <div class="card" data-categoria="{dc}">\n'
        f'        <div class="card-img-wrapper">\n'
        f'          <img class="card-img" src="{rel}" alt="{t}">\n'
        f'          <span class="card-badge {bcls}">{btxt}</span>\n'
        f"        </div>\n"
        f'        <div class="card-body">\n'
        f'          <div class="card-cat">Oferta #{num:02d}</div>\n'
        f'          <h3 class="card-title">{t}</h3>\n'
        f'          <p class="card-desc">Oferta especial direto na Shopee, '
        f'aproveite enquanto durar o estoque!</p>\n'
        f'          <a href="{url}" target="_blank" rel="noopener noreferrer" '
        f'class="btn-buy">Ver Oferta na Shopee 🛒</a>\n'
        f"        </div>\n"
        f"      </div>"
    )


def rebuild(reg):
    """Delega a geracao da pagina ao gerador deterministico."""
    salvar_registro(reg)
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "ferramentas", "gera_pagina.py")],
        capture_output=True,
        text=True,
    )
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-400:])
    if r.returncode != 0:
        print("GERADOR FALHOU!")





def main():
    reg = carregar_registro()
    novos, trocas, rems = parse_pedidos()
    mudanca = bool(novos or trocas or rems)

    if rems:
        antes = len(reg)
        reg = [r for r in reg if r["num"] not in rems]
        print(f"removidos: {antes - len(reg)}")

    for num, u in trocas.items():
        achou = False
        for r in reg:
            if r["num"] == num:
                r["url"] = u
                r["key"] = url_key(u)
                r["title"] = ""
                antiga = r.get("img_path", "")
                if antiga and os.path.exists(os.path.join(ROOT, antiga)):
                    os.remove(os.path.join(ROOT, antiga))
                r["img_path"] = ""
                achou = True
        if not achou:
            reg.append(
                {"num": num, "key": url_key(u), "url": u, "title": "", "img_path": ""}
            )
        print(f"substituicao marcada: #{num}")

    prox = max([r["num"] for r in reg], default=0) + 1
    for u in novos:
        if any(r.get("url") == u for r in reg):
            print(f"ja existe: {u[:60]}")
            continue
        reg.append(
            {"num": prox, "key": url_key(u), "url": u, "title": "", "img_path": ""}
        )
        print(f"novo produto #{prox}: {u[:60]}")
        prox += 1

    salvar_registro(reg)

    results = []
    alterou = False
    for r in sorted(reg, key=lambda x: x["num"]):
        tem_img = bool(r.get("img_path")) and os.path.exists(
            os.path.join(ROOT, r["img_path"])
        )
        bom_titulo = not titulo_ruim(r.get("title"))
        print(f"[#{r['num']:02d}] {r['url'][:60]}")

        if tem_img and bom_titulo:
            results.append(r)
            continue
        alterou = True

        if tem_img and not bom_titulo:
            print("  buscando apenas titulo...")
            try:
                fin, _, _ = http_get(r["url"], timeout=30)
            except Exception:
                fin = r["url"]
            novo_t = fetch_name_only(fin)
            if titulo_ruim(novo_t):
                t2, _ = via_playwright(fin or r["url"])
                novo_t = t2 or ""
            if titulo_ruim(novo_t):
                print("  mantendo titulo anterior")
                novo_t = r.get("title", "")
            r["title"] = novo_t
            results.append(r)
            continue

        d = get_link_data(r["url"])
        if not d or not d[1]:
            if tem_img:
                print("  coleta falhou, mantendo imagem anterior")
                results.append(r)
                continue
            print("  SEM DADOS - produto fica fora da pagina")
            continue
        title, fp = d
        if titulo_ruim(title):
            tn = fetch_name_only(r["url"])
            if not titulo_ruim(tn):
                title = tn
        final_name = f"produto_{r['num']:02d}{os.path.splitext(fp)[1]}"
        final_fp = "img/" + final_name
        antiga = r.get("img_path", "")
        if antiga and os.path.exists(os.path.join(ROOT, antiga)):
            os.remove(os.path.join(ROOT, antiga))
        os.replace(fp, os.path.join(ROOT, final_fp))
        r["title"] = title
        r["img_path"] = final_fp
        r["key"] = url_key(r["url"])
        results.append(r)
        print(f"  OK: {title!r}")

    salvar_registro(results)

    if alterou or mudanca:
        rebuild([r for r in results if r.get("img_path")])

    if os.path.isdir(PEDIDOS_DIR):
        for fn in os.listdir(PEDIDOS_DIR):
            os.remove(os.path.join(PEDIDOS_DIR, fn))
    print(f"fim: {len(results)} produto(s)")


if __name__ == "__main__":
    main()
