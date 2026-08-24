#!/usr/bin/env python3
"""Aplica pacote SEO: robots.txt, sitemap.xml, meta tags no index.html
e integra tudo ao gera_pagina.py (idempotente)."""
import os
import re

ROOT = "/home/daytona/tgbot/vitrine"
os.chdir(ROOT)

URL = "https://aalexaalmeida108-cmd.github.io/loja/"
TITLE = (
    "Ofertas Shopee - Ferramentas, Automotivo e Mobilidade Elétrica | Achadinhos"
)
DESC = (
    "As melhores ofertas da Shopee com frete grátis: ferramentas profissionais, "
    "acessórios automotivos e de moto, mobilidade elétrica e eletrônicos. "
    "Preços imbatíveis direto dos fornecedores!"
)
IMG = URL + "img/produto_03.jpg"

# ---------- robots.txt ----------
with open("robots.txt", "w", encoding="utf-8") as f:
    f.write("User-agent: *\nAllow: /\n\nSitemap: " + URL + "sitemap.xml\n")

# ---------- sitemap.xml ----------
from datetime import date

with open("sitemap.xml", "w", encoding="utf-8") as f:
    f.write(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        "  <url>\n"
        "    <loc>" + URL + "</loc>\n"
        "    <lastmod>" + date.today().isoformat() + "</lastmod>\n"
        "    <changefreq>daily</changefreq>\n"
        "    <priority>1.0</priority>\n"
        "  </url>\n"
        "</urlset>\n"
    )
print("robots.txt + sitemap.xml ok")

# ---------- index.html ----------
html = open("index.html", encoding="utf-8").read()
if "og:title" not in html:
    seo_block = (
        "<title>" + TITLE + "</title>\n"
        '    <meta name="description" content="' + DESC + '">\n'
        '    <meta name="robots" content="index, follow">\n'
        '    <link rel="canonical" href="' + URL + '">\n'
        '    <meta property="og:type" content="website">\n'
        '    <meta property="og:site_name" content="Achadinhos Shopee">\n'
        '    <meta property="og:title" content="' + TITLE + '">\n'
        '    <meta property="og:description" content="' + DESC + '">\n'
        '    <meta property="og:image" content="' + IMG + '">\n'
        '    <meta property="og:url" content="' + URL + '">\n'
        '    <meta name="twitter:card" content="summary_large_image">\n'
        '    <meta name="twitter:title" content="' + TITLE + '">\n'
        '    <meta name="twitter:description" content="' + DESC + '">\n'
        '    <meta name="twitter:image" content="' + IMG + '">'
    )
    html = re.sub(
        r"<title>.*?</title>", seo_block, html, count=1, flags=re.S
    )
    open("index.html", "w", encoding="utf-8").write(html)
    print("index.html: SEO aplicado")
else:
    print("index.html: SEO ja presente")

# ---------- gera_pagina.py ----------
gp = os.path.join("ferramentas", "gera_pagina.py")
src = open(gp, encoding="utf-8").read()
mudou = False

if "SEO_TITLE" not in src:
    inj = '''
SEO_TITLE = __T__
SEO_DESC = __D__
SEO_URL = __U__
SEO_IMG = __I__


def aplicar_seo(tpl):
    bloco = (
        "<title>" + SEO_TITLE + "</title>\\n"
        '    <meta name="description" content="' + SEO_DESC + '">\\n'
        '    <meta name="robots" content="index, follow">\\n'
        '    <link rel="canonical" href="' + SEO_URL + '">\\n'
        '    <meta property="og:type" content="website">\\n'
        '    <meta property="og:site_name" content="Achadinhos Shopee">\\n'
        '    <meta property="og:title" content="' + SEO_TITLE + '">\\n'
        '    <meta property="og:description" content="' + SEO_DESC + '">\\n'
        '    <meta property="og:image" content="' + SEO_IMG + '">\\n'
        '    <meta property="og:url" content="' + SEO_URL + '">\\n'
        '    <meta name="twitter:card" content="summary_large_image">\\n'
        '    <meta name="twitter:title" content="' + SEO_TITLE + '">\\n'
        '    <meta name="twitter:description" content="' + SEO_DESC + '">\\n'
        '    <meta name="twitter:image" content="' + SEO_IMG + '">'
    )
    return re.sub(r"<title>.*?</title>", bloco, tpl, count=1, flags=re.S)


'''.replace("__T__", repr(TITLE)).replace("__D__", repr(DESC)).replace(
        "__U__", repr(URL)
    ).replace("__I__", repr(IMG))
    anchor = "def gerar(reg=None):"
    assert anchor in src, "anchor gera ausente"
    if anchor not in src.split("aplicar_seo")[0] or True:
        pass
    # inserir defs ANTES de gerar
    idx = src.find(anchor)
    # evita duplicar caso aplicar_seo ja exista no arquivo
    src = src[:idx] + inj + "\n" + src[idx:]
    mudou = True

old_call = '''    tpl = re.sub(r"<script>.*?</script>", "", tpl, flags=re.S)'''
new_call = old_call + "\n    tpl = aplicar_seo(tpl)"
if "tpl = aplicar_seo(tpl)" not in src:
    assert old_call in src, "call point ausente"
    src = src.replace(old_call, new_call, 1)
    mudou = True

if mudou:
    open(gp, "w", encoding="utf-8").write(src)
    print("gera_pagina.py integrado ao SEO")
else:
    print("gera_pagina.py ja integrado")
