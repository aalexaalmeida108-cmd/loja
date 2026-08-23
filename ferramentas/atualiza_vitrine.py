#!/usr/bin/env python3
"""Busca imagens dos produtos a partir dos links em pedidos/ e atualiza a vitrine."""
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


def http_get(url: str, timeout: int = 30) -> tuple:
    req = Request(url, headers={"User-Agent": UA, "Accept-Language": "pt-BR,pt;q=0.9"})
    with urlopen(req, timeout=timeout) as r:
        final = r.geturl()
        data = r.read()
        ctype = r.headers.get("content-type", "")
    return final, data, ctype


def extract_og_image(html: str, base_url: str):
    m = re.search(
        r"<meta[^>]+property=[\"']og:image[\"'][^>]+content=[\"']([^\"']+)",
        html,
    )
    if not m:
        m = re.search(
            r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:image[\"']",
            html,
        )
    if not m:
        # JSON-LD (Shopee usa)
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
    return urljoin(base_url, m.group(1))


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
        try:
            final, data, ctype = http_get(url)
            if "image/" in ctype:
                img_bytes = data
                img_url = final
            else:
                html_txt = data.decode("utf-8", errors="replace")
                img_url = extract_og_image(html_txt, final)
                if not img_url:
                    print(f"sem og:image: {url}")
                    continue
                _, img_bytes, _ = http_get(img_url)
            key = url_key(url)

            alvo = None
            for s, e in card_blocks(html):
                blk = html[s:e]
                if "card-img" not in blk and key in blk:
                    alvo = (s, e)
                    break
            if alvo is None:
                for s, e in card_blocks(html):
                    if "card-img" not in html[s:e]:
                        alvo = (s, e)
                        break
            if alvo is None:
                print("todos os cards tem imagem; descartando", url)
                continue

            ext = ".jpg"
            if "png" in ctype or ".png" in img_url.lower():
                ext = ".png"
            elif "webp" in ctype or ".webp" in img_url.lower():
                ext = ".webp"
            rel = f"img/produto_{seq:02d}{ext}"
            with open(os.path.join(ROOT, rel), "wb") as f:
                f.write(img_bytes)
            seq += 1

            html = insert_img(html, alvo[0], alvo[1], rel)
            feitos += 1
            print(f"ok: {url} -> {rel}")
        except Exception as exc:
            print(f"falha {url}: {exc}")

    if feitos:
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(html)

    # limpa pedidos processados
    if os.path.isdir(PEDIDOS_DIR):
        for fn in os.listdir(PEDIDOS_DIR):
            os.remove(os.path.join(PEDIDOS_DIR, fn))

    print(f"concluido: {feitos} imagem(ns)")


if __name__ == "__main__":
    main()
