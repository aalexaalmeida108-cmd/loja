#!/usr/bin/env python3
"""Bateria de testes v2: inclui API oficial com IDs extraidos."""
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


for num, url in PROBLEMAS.items():
    print(f"=== LINK {num}: {url}")
    final = url
    try:
        req = Request(url, headers={"User-Agent": UA})
        with urlopen(req, timeout=30) as r:
            final = r.geturl()
        print(f"  final: {final[:100]}")
    except Exception as e:
        print(f"  resolve falhou: {str(e)[:80]}")

    # API oficial com IDs (padroes opaanlp, -i., /product/)
    m = (
        re.search(r"/opaanlp/(\d+)/(\d+)", final)
        or re.search(r"-i\.(\d+)\.(\d+)", final)
        or re.search(r"/product/(\d+)/(\d+)", final)
    )
    if m:
        shop, item = m.group(1), m.group(2)
        print(f"  IDs: shop={shop} item={item}")
        for ep in (
            f"https://shopee.com.br/api/v4/pdp/get_pc?item_id={item}&shop_id={shop}&detail_level=0",
            f"https://mall.shopee.com.br/api/v2/item/get?itemid={item}&shopid={shop}",
        ):
            try:
                req2 = Request(
                    ep,
                    headers={
                        "User-Agent": UA,
                        "Referer": final,
                        "X-API-SOURCE": "pc",
                        "Accept": "application/json",
                    },
                )
                d = json.loads(urlopen(req2, timeout=30).read())
                it = d.get("item") or (d.get("data") or {}).get("item") or {}
                nome = str(it.get("name", "(vazio)"))
                qtd = len(it.get("images", []))
                print(f"  [api] nome={nome[:70]!r} | images={qtd}")
                if it.get("images"):
                    im0 = it["images"][0]
                    if not str(im0).startswith("http"):
                        im0 = "https://cf.shopee.com.br/file/" + str(im0)
                    print(f"     img0: {im0[:90]}")
                if nome != "(vazio)":
                    break
            except Exception as e:
                print(f"  [api] ERRO {ep[:55]}: {str(e)[:60]}")
    else:
        print("  sem IDs na URL final!")

print("FIM DOS TESTES")
