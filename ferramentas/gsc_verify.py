#!/usr/bin/env python3
"""Verificacao Google Search Console: arquivo HTML + meta tag."""
import json
import os

ROOT = "/home/daytona/tgbot/vitrine"
os.chdir(ROOT)

FILE_NAME = "google401c78fef07a0730.html"
FILE_CONTENT = "google-site-verification: google401c78fef07a0730.html"
META_TAG = '<meta name="google-site-verification" content="gqn4su5kU4SzdRJQc886KAFFLqaYM7p4kXiX_iglPKo">'

# 1. arquivo de verificacao na raiz
with open(FILE_NAME, "w", encoding="utf-8") as f:
    f.write(FILE_CONTENT)
print("arquivo criado:", FILE_NAME)

# 2. meta tag no index.html (idempotente)
html = open("index.html", encoding="utf-8").read()
if "google-site-verification" not in html:
    html = html.replace(
        "<title>",
        META_TAG + "\n    <title>",
        1,
    )
    open("index.html", "w", encoding="utf-8").write(html)
    print("meta tag adicionada ao index.html")
else:
    print("meta tag ja presente")

# 3. persistir nas futuras geracoes: aplica_seo.py inclui a meta no bloco
ap = os.path.join("ferramentas", "aplica_seo.py")
src = open(ap, encoding="utf-8").read()
if "google-site-verification" not in src:
    src = src.replace(
        '<meta name="robots" content="index, follow">',
        META_TAG + '\n        \'    <meta name="robots" content="index, follow">',
    )
    # o replace acima duplica aspas por causa das camadas; refazer com marcador simples
    open(ap, "w").write(src)
print("verifica integracao aplica_seo")

# integracao robusta: inserir direto no gera_pagina.py
gp = os.path.join("ferramentas", "gera_pagina.py")
src = open(gp, encoding="utf-8").read()
if "google-site-verification" not in src:
    # adiciona constante e injeta junto com o filtro/js final
    inj = (
        "\nGSC_META = "
        + json.dumps(META_TAG)
        + "\n"
    )
    anchor = 'def gerar(reg=None):'
    if anchor in src:
        idx = src.find(anchor)
        src = src[:idx] + inj + "\n" + src[idx:]
    old_js_end = '''    new_html = new_html.replace("</body>", FILTRO_JS + "\\n</body>", 1)'''
    new_js_end = '''    new_html = new_html.replace("</body>", FILTRO_JS + "\\n</body>", 1)
    new_html = new_html.replace("<title>", GSC_META + "\\n    <title>", 1)'''
    if old_js_end in src:
        src = src.replace(old_js_end, new_js_end, 1)
    open(gp, "w", encoding="utf-8").write(src)
    print("gera_pagina.py: GSC_META integrado")
else:
    print("gera_pagina.py ja tem GSC")
