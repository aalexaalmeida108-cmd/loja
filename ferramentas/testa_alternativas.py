#!/usr/bin/env python3
"""Bateria de testes de metodos alternativos para os links bloqueados."""
import json
import re
import urllib.parse
from urllib.request import Request, urlopen

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126 Safari/537.36"
)

PROBLEMAS = {
    "01": "https://s.shopee.com.br/2qU05vxDvw",
    "05": "https://s.shopee.com.br/3qMXHriOq2",
    "09": "https://s.shopee.com.br/3qMXHxfuNF",
    "11": "https://s.shopee.com.br/5ArusTHcJz",
    "12": "https://s.shopee.com.br/2gAZttMC2F",
}

OG_RE = re.compile(r'property=["\']og:title["\'][^>]+content=["\']([^"\']+)')
OGI_RE = re.compile(r'property=["\']og:image["\'][^>]+content=["\']([^"\']+)')
TT_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.I)
CDN_RE = re.compile(
    r"https://(?:cf\.shopee\.com\.br|down-[a-z-]*\.img\.susercontent\.com|[a-z0-9.-]*img\.susercontent\.com)/file/[A-Za-z0-9._-]{10,}"
)


def get(url, timeout=45):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=timeout) as r:
        return r.read()


def analisa(tag, txt, base):
    t = ""
    m = OG_RE.search(txt) or TT_RE.search(txt)
    if m:
        t = m.group(1)[:60]
    imgs = []
    seen = set()
    m2 = OGI_RE.search(txt)
    if m2:
        imgs.append(m2.group(1))
    for m3 in CDN_RE.finditer(txt):
        u = m3.group(0)
        if u not in seen:
            seen.add(u)
            imgs.append(u)
    print(f"    [{tag}] titulo={t!r} | imgs={len(imgs)}")
    for u in imgs[:2]:
        print(f"       {u[:90]}")
    return bool(t and "shopee brasil" not in t.lower()) or len(imgs) > 0


for num, url in PROBLEMAS.items():
    print(f"=== LINK {num}: {url}")
    # resolve final
    final = url
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=30) as r:
            final = r.geturl()
        print(f"  final: {final[:100]}")
    except Exception as e:
        print(f"  resolve falhou: {str(e)[:80]}")

    enc = urllib.parse.quote(final, safe="")

    # 1. AllOrigins
    try:
        txt = get(f"https://api.allorigins.win/raw?url={enc}").decode("utf-8", "replace")
        analisa("allorigins", txt, final)
    except Exception as e:
        print(f"    [allorigins] ERRO: {str(e)[:80]}")

    # 2. CodeTabs
    try:
        txt = get(f"https://api.codetabs.com/v1/proxy?quest={enc}").decode("utf-8", "replace")
        analisa("codetabs", txt, final)
    except Exception as e:
        print(f"    [codetabs] ERRO: {str(e)[:80]}")

    # 3. CorsProxy
    try:
        txt = get(f"https://corsproxy.io/?url={enc}").decode("utf-8", "replace")
        analisa("corsproxy", txt, final)
    except Exception as e:
        print(f"    [corsproxy] ERRO: {str(e)[:80]}")

    # 4. site mobile direto
    try:
        mob = final.replace("shopee.com.br", "m.shopee.com.br")
        txt = get(mob).decode("utf-8", "replace")
        analisa("mobile", txt, mob)
    except Exception as e:
        print(f"    [mobile] ERRO: {str(e)[:80]}")

    # 5. Wayback
    try:
        d = json.loads(
            get(f"http://archive.org/wayback/available?url={urllib.parse.quote(final)}", 20)
        )
        snap = d.get("archived_snapshots", {}).get("closest", {})
        if snap.get("url"):
            print(f"    [wayback] snapshot: {snap['url'][:90]}")
            txt = get(snap["url"]).decode("utf-8", "replace")
            analisa("wayback", txt, final)
        else:
            print("    [wayback] sem snapshot")
    except Exception as e:
        print(f"    [wayback] ERRO: {str(e)[:80]}")

print("FIM DOS TESTES")
