#!/usr/bin/env python3
"""Busca imagens dos produtos a partir dos links em pedidos/ e atualiza a vitrine."""
import json
import os
import re
import shutil
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


def http_get(url: str, timeout: int = 30) -> tuple:
    req = Request(
        url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"}
    )
    with urlopen(req, timeout=timeout) as r:
        final = r.geturl()
        data = r.read()
        ctype = r.headers.get("content-type", "")
    return final, data, ctype


def fetch_via_jina(url: str) -> str:
    req = Request("https://r.jina.ai/" + url, headers={"User-Agent": UA})
    with urlopen(req, timeout=90) as r:
        return r.read().decode("utf-8", errors="replace")


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


def card_blocks(html: str):
    starts = [m.start() for m in re.finditer(r"<div class=\"card\"", html)]
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(html)
        yield s, e


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


def insert_img(html: str, s: int, e: int, rel: str) -> str:
    blk = html[s:e]
    tag = f'<img class="card-img" src="{rel}" alt="Produto">'
    new_blk, k = re.subn(
        r"<span class=\"card-icon\">[^<]*</span>", tag, blk, count=1
    )
    if k == 0:
        new_blk = re.sub(
            r"(<div class=\"card-img-wrapper\">)",
            r"\1\n          " + tag,
            blk,
            count=1,
        )
    out = html[:s] + new_blk + html[e:]
    return ensure_css(out)


def process_url(url: str):
    """Retorna (img_bytes, ext) ou None."""
    try:
        final, data, ctype = http_get(url)
    except Exception as exc:
        print(f"abertura falhou {url}: {exc}")
        return None
    if "image/" in ctype:
        ext = ".jpg"
        if "png" in ctype:
            ext = ".png"
        elif "webp" in ctype:
            ext = ".webp"
        return data, ext

    html_txt = data.decode("utf-8", errors="replace")
    img_url = extract_any_image(html_txt, final)
    if not img_url:
        print(f"sem imagem no HTML | len={len(html_txt)} | tentando jina...")
        try:
            md = fetch_via_jina(final)
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
    return img_bytes, ext


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

    feitos = 0
    for url in pendencias:
        res = process_url(url)
        if not res:
            continue
        img_bytes, ext = res
        key = url_key(url)

        alvo = None
        for s, e in card_blocks(html):
            blk = html[s:e]
            if 'class="card-img"' not in blk and key in blk:
                alvo = (s, e)
                break
        if alvo is None:
            for s, e in card_blocks(html):
                if 'class="card-img"' not in html[s:e]:
                    alvo = (s, e)
                    break
        if alvo is None:
            print("todos os cards tem imagem; descartando", url)
            continue

        rel = f"img/produto_{seq:02d}{ext}"
        with open(os.path.join(ROOT, rel), "wb") as f:
            f.write(img_bytes)
        seq += 1

        html = insert_img(html, alvo[0], alvo[1], rel)
        feitos += 1
        print(f"ok: {url} -> {rel}")

    if feitos:
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(html)

    if os.path.isdir(PEDIDOS_DIR):
        for fn in os.listdir(PEDIDOS_DIR):
            os.remove(os.path.join(PEDIDOS_DIR, fn))

    print(f"concluido: {feitos} imagem(ns)")


if __name__ == "__main__":
    main()
