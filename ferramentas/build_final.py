#!/usr/bin/env python3
"""Constroi o index.html final do zero a partir do original canonico."""
import json
import os
import re
import subprocess
import sys

ROOT = "/home/daytona/tgbot/vitrine"
sys.path.insert(0, os.path.join(ROOT, "ferramentas"))
import coleta_dados as cd

# 1. pagina original integra
orig = subprocess.run(
    ["git", "show", "60ad3f3:index.html"], cwd=ROOT, capture_output=True, text=True
).stdout

# 2. registro com categorias
reg = cd.carregar_registro()
for r in reg:
    if not r.get("categoria"):
        r["categoria"] = cd.classifica_categoria(r.get("title", ""))
cd.salvar_registro(reg)

visiveis = [
    r for r in sorted(reg, key=lambda x: x["num"])
    if r.get("img_path") and os.path.exists(os.path.join(ROOT, r["img_path"]))
]
print(f"produtos visiveis: {len(visiveis)}")

cards = []
usadas = set()
cats = []
for r in visiveis:
    rel = "img/" + os.path.basename(r["img_path"])
    usadas.add(os.path.basename(r["img_path"]))
    if r["categoria"] not in cats:
        cats.append(r["categoria"])
    cards.append(
        cd.make_card(r["num"], rel, r["url"], r.get("title", ""), r["categoria"])
    )

# limpa imagens nao usadas
import glob
for f in glob.glob(os.path.join(ROOT, "img", "*")):
    if os.path.basename(f) not in usadas:
        os.remove(f)

# 3. menu de categorias
botoes = ['<button class="cat-btn active" data-cat="todos">Todos</button>']
for c in sorted(cats):
    botoes.append(
        f'<button class="cat-btn" data-cat="{c}">{c}</button>'
    )
pills = (
    '<div class="cats" id="catMenu">\n'
    + "\n".join("        " + b for b in botoes)
    + "\n      </div>"
)
filtro_js = (
    "<script>\n"
    "(function(){\n"
    "function aplicarFiltros(){\n"
    "var termo=(document.getElementById('searchInput')?"
    "document.getElementById('searchInput').value:'').toLowerCase().trim();\n"
    "var ativa=document.querySelector('.cat-btn.active');\n"
    "var cat=ativa?ativa.getAttribute('data-cat'):'todos';\n"
    "document.querySelectorAll('#productGrid .card').forEach(function(c){\n"
    "var txt=((c.querySelector('.card-title')||{textContent:''}).textContent||'')"
    "+' '+((c.querySelector('.card-desc')||{textContent:''}).textContent||'');\n"
    "var okCat=(cat==='todos'||c.getAttribute('data-categoria')===cat);\n"
    "var okBusca=!termo||txt.toLowerCase().indexOf(termo)!==-1;\n"
    "c.style.display=(okCat&&okBusca)?'':'none';\n"
    "});\n"
    "}\n"
    "window.filterItems=aplicarFiltros;\n"
    "var si=document.getElementById('searchInput');\n"
    "if(si){si.addEventListener('keyup',aplicarFiltros);"
    "si.addEventListener('input',aplicarFiltros);}\n"
    "var bs=document.querySelectorAll('.cat-btn');\n"
    "bs.forEach(function(b){b.addEventListener('click',function(){\n"
    "bs.forEach(function(x){x.classList.remove('active');});\n"
    "b.classList.add('active');aplicarFiltros();\n"
    "});});\n"
    "})();\n"
    "\n</script>"
)

# 4. monta novo html substituindo o conteudo do grid do original
DIV_RE = re.compile(r"<div\b|</div>")
g0 = orig.find('<div class="grid" id="productGrid">')
depth = 0
i = g0
while i < len(orig):
    m = DIV_RE.search(orig, i)
    if not m:
        break
    if m.group(0) == "</div>":
        depth -= 1
        if depth == 0:
            break
    else:
        depth += 1
    i = m.end()

body_start = orig.find(">", g0) + 1
new_html = orig[:body_start] + "\n" + "\n".join(cards) + "\n      " + orig[i:]

# css dos filtros e das imagens
extra_css = ""
if ".card-img {" not in new_html:
    extra_css += (
        "    .card-img {\n"
        "      position: absolute;\n"
        "      inset: 0;\n"
        "      width: 100%;\n"
        "      height: 100%;\n"
        "      object-fit: cover;\n"
        "    }\n"
    )
extra_css += (
    "    .cats {\n"
    "      display: flex;\n"
    "      flex-wrap: wrap;\n"
    "      gap: 10px;\n"
    "      justify-content: center;\n"
    "      padding: 0 20px 28px;\n"
    "    }\n"
    "    .cat-btn {\n"
    "      background: rgba(255,255,255,0.06);\n"
    "      color: #f8fafc;\n"
    "      border: 1px solid rgba(255,255,255,0.15);\n"
    "      padding: 9px 18px;\n"
    "      border-radius: 999px;\n"
    "      cursor: pointer;\n"
    "      font-family: inherit;\n"
    "      font-size: 0.92rem;\n"
    "      font-weight: 700;\n"
    "      transition: all 0.2s;\n"
    "    }\n"
    "    .cat-btn:hover { border-color: #ee4d2d; }\n"
    "    .cat-btn.active {\n"
    "      background: #ee4d2d;\n"
    "      border-color: #ee4d2d;\n"
    "      color: #fff;\n"
    "    }\n"
)
new_html = new_html.replace("</style>", extra_css + "  </style>", 1)

# menu antes do grid e script antes de fechar body
gi = new_html.find('<div class="grid" id="productGrid">')
new_html = new_html[:gi] + pills + "\n" + new_html[gi:]
new_html = new_html.replace("</body>", filtro_js + "\n</body>", 1)

with open(os.path.join(ROOT, "index.html"), "w", encoding="utf-8") as f:
    f.write(new_html)

sem_com = re.sub(r"<!--.*?-->", "", new_html, flags=re.S)
o = len(re.findall(r"<div\b", sem_com))
c = sem_com.count("</div>")
print(f"divs: {o}/{c} -> {'OK' if o == c else 'QUEBRADO'}")
print(f"menus: {new_html.count('catMenu')} | scripts: {new_html.count('var bs=')}")
print(f"categorias: {sorted(cats)}")
