#!/usr/bin/env python3
"""Busca imagens/titulos dos links em pedidos/, cria ou preenche cards na vitrine."""
import json
import os
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(ROOT, "img")
PEDIDOS_DIR = os.path.join(ROOT, "pedidos")

SHOPEE_CDN_RE = re.compile(
    r"https://[a-z0-9.-]*img\.susercontent\.com/[A-Za-z0-9._/-]+"
)
IMG_ANY_RE = re.compile(
    r"https?://[^\s\"'\\)<>]+?\.(?:jpe?g|png|webp)(?:\?[A-Za-z0-9&=._%-]*)?"
)
OG_RE = re.compile(
    r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)"
)
OG_RE2 = re.compile(
    r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:image[\"']"
)
TW_RE = re.compile(
    r"<meta[^>]+name=[\"']twitter:image[\"'][^>]+content=[\"']([^\"']+)"
)
OG_TITLE_RE = re.compile(
    r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)"
)
BADGES = [
    ("badge-hot", "Destaque"),
    ("badge-toprated", "Mais Vendido"),
    ("badge-shipping", "Frete Grátis"),
]


def http_get(url: str, timeout: int = 30) -> tuple:
    req = Request(
        url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    )
    with urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(), r.headers.get("content-type", "")


def fetch_via_jina(url: str) -> str:
    req = Request("https://r.jina.ai/" + url, headers={"User-Agent": UA})
    with urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", errors="replace")


def clean_title(t: str) -> str:
    t = re.sub(r"\s*\|.*$", "", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t[:80] if t else ""


def extract_title(html_txt: str) -> str:
    m = OG_TITLE_RE.search(html_txt)
    if m:
        return clean_title(m.group(1))
    m = re.search(r"<title[^>]*>([^<]+)</title>", html_txt, re.I)
    if m:
        return clean_title(m.group(1))
    return ""


def extract_og_image(html: str, base_url: str):
    m = OG_RE.search(html) or OG_RE2.search(html) or TW_RE.search(html)
    if m:
        return urljoin(base_url, m.group(1))
    for m2 in re.finditer(r"<script[^>]+ld\+json[^>]*>(.*?)</script>", html, re.S):
        try:
            d = json.loads(m2.group(1))
        except Exception:
            continue
        img = d.get("image")
        if isinstance(img, str):
            return urljoin(base_url, img)
        if isinstance(img, list) and img:
            return urljoin(base_url, img[0])
    return None


def extract_any_image(text: str, base_url: str):
    u = extract_og_image(text, base_url)
    if u:
        return u
    m = SHOPEE_CDN_RE.search(text)
    if m:
        u = m.group(0)
        if not re.search(r"\.(jpe?g|png|webp)$", u):
            u += ".webp"
        return u
    m = IMG_ANY_RE.search(text)
    if m:
        return m.group(0)
    return None


def url_key(url: str) -> str:
    m = re.search(r"shopee\.com\.br/([A-Za-z0-9._-]{6,})", url)
    if m:
        return m.group(1)
    u = re.sub(r"[?#].*$", "", url)
    return u.rstrip("/").split("/")[-1] or u


def ensure_css(html: str) -> str:
    if ".card-img {" in html:
        return html
    css = (
        "    .card-img {\n"
        "      position: absolute;\n"
        "      inset: 0;\n"
        "      width: 100%;\n"
        "      height: 100%;\n"
        "      object-fit: cover;\n"
        "    }\n"
    )
    return html.replace("</style>", css + "  </style>", 1)


def process_url(url: str):
    """Retorna (img_bytes, ext, titulo) ou None."""
    final = url
    try:
        final, data, ctype = http_get(url)
    except Exception as exc:
        print(f"abertura falhou {url}: {exc}")
        return None
    html_txt = ""
    if "image/" in ctype:
        ext = ".jpg"
        if "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        return data, ext, ""
    html_txt = data.decode("utf-8", errors="replace")
    titulo = extract_title(html_txt)
    img_url = extract_any_image(html_txt, final)
    if not img_url:
        print(f"sem imagem no HTML | len={len(html_txt)} | tentando jina...")
        try:
            md = fetch_via_jina(final)
            if not titulo:
                titulo = extract_title(md)
            img_url = extract_any_image(md, final)
        except Exception as je:
            print(f"jina falhou {final}: {je}")
    if not img_url:
        print(f"desistindo de {url} | final={final} | len={len(html_txt)}")
        return None
    try:
        _, img_bytes, ctype2 = http_get(img_url)
    except Exception as ie:
        print(f"download da imagem falhou {img_url}: {ie}")
        return None
    ext = ".jpg"
    low = img_url.lower()
    if ".png" in low or "png" in ctype2:
        ext = ".png"
    elif ".webp" in low or "webp" in ctype2:
        ext = ".webp"
    return img_bytes, ext, titulo


def make_card(num: int, rel: str, url: str, titulo: str) -> str:
    badge_cls, badge_txt = BADGES[(num - 1) % len(BADGES)]
    t = titulo or f"Produto Oferta #{num:02d}"
    esc = (
        t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    return (
        f'\n      <!-- Item {num:02d} -->\n'
        f'      <div class="card" data-title="{esc}">\n'
        f'        <div class="card-img-wrapper">\n'
        f'          <img class="card-img" src="{rel}" alt="{esc}">\n'
        f'          <span class="card-badge {badge_cls}">{badge_txt}</span>\n'
        f"        </div>\n"
        f'        <div class="card-body">\n'
        f'          <div class="card-cat">Eletroeletrônicos #{num:02d}</div>\n'
        f'          <h3 class="card-title">{esc}</h3>\n'
        f'          <p class="card-desc">Oferta especial direto na Shopee, '
        f'aproveite enquanto durar o estoque!</p>\n'
        f'          <a href="{url}" target="_blank" rel="noopener noreferrer" '
        f'class="btn-buy">Ver Oferta na Shopee 🛒</a>\n'
        f"        </div>\n"
        f"      </div>"
    )


def main():
    idx_path = os.path.join(ROOT, "index.html")
    with open(idx_path, encoding="utf-8") as f:
        html = f.read()

    os.makedirs(IMG_DIR, exist_ok=True)
    seq = len([f for f in os.listdir(IMG_DIR) if f.startswith("produto_")]) + 1

    pendencias = []
    if os.path.isdir(PEDIDOS_DIR):
        for fn in sorted(os.listdir(PEDIDOS_DIR)):
            p = os.path.join(PEDIDOS_DIR, fn)
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    pendencias += [
                        ln.strip() for ln in f if ln.strip().startswith("http")
                    ]

    grid_open = html.find('<div class="grid" id="productGrid">')
    insert_at = grid_open + len('<div class="grid" id="productGrid">') if grid_open >= 0 else -1

    feitos = 0
    criados = 0
    novos_blocos = []
    for url in pendencias:
        key = url_key(url)

        # ja existe card com esse link?
        starts = [m.start() for m in re.finditer(r'<div class="card"', html)]
        blocks = []
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(html)
            blocks.append((s, e))

        alvo_existente = None
        vago = None
        for s, e in blocks:
            blk = html[s:e]
            tem_img = 'class="card-img"' in blk
            if key in blk and not tem_img:
                alvo_existente = (s, e)
                break
            if not tem_img and vago is None:
                vago = (s, e)

        res = process_url(url)
        if not res:
            continue
        img_bytes, ext, titulo = res

        rel = f"img/produto_{seq:02d}{ext}"
        with open(os.path.join(ROOT, rel), "wb") as f:
            f.write(img_bytes)
        seq += 1

        if alvo_existente is not None:
            s, e = alvo_existente
            blk = html[s:e]
            tag = f'<img class="card-img" src="{rel}" alt="Produto">'
            nb, k = re.subn(
                r"<span class=\"card-icon\">[^<]*</span>", tag, blk, count=1
            )
            if k == 0:
                nb = re.sub(
                    r"(<div class=\"card-img-wrapper\">)",
                    r"\1\n          " + tag,
                    blk,
                    count=1,
                )
            html = html[:s] + nb + html[e:]
            feitos += 1
            print(f"preenchido: {url} -> {rel}")
        elif vago is not None:
            s, e = vago
            blk = html[s:e]
            tag = f'<img class="card-img" src="{rel}" alt="Produto">'
            nb, k = re.subn(
                r"<span class=\"card-icon\">[^<]*</span>", tag, blk, count=1
            )
            if k == 0:
                nb = re.sub(
                    r"(<div class=\"card-img-wrapper\">)",
                    r"\1\n          " + tag,
                    blk,
                    count=1,
                )
            html = html[:s] + nb + html[e:]
            feitos += 1
            print(f"vago preenchido: {url} -> {rel}")
        elif insert_at >= 0:
            num = html.count('<div class="card"') + criados + 1
            novos_blocos.append(make_card(num, rel, url, titulo))
            criados += 1
            print(f"card criado: {url} -> {rel} ({titulo!r})")
        else:
            print("sem grid na pagina; descartando", url)

    if criados and insert_at >= 0:
        bloco = "\n".join(novos_blocos) + "\n"
        html = html[:insert_at] + bloco + html[insert_at:]
    if feitos or criados:
        html = ensure_css(html)
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(html)

    if os.path.isdir(PEDIDOS_DIR):
        for fn in os.listdir(PEDIDOS_DIR):
            os.remove(os.path.join(PEDIDOS_DIR, fn))

    print(f"concluido: {feitos} preenchido(s), {criados} criado(s)")


if __name__ == "__main__":
    main()
