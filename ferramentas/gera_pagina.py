#!/usr/bin/env python3
"""GERADOR DA PAGINA — unica fonte de verdade.
Reconstroi o index.html INTEIRO a partir do produtos.json + template base.
Nada de cirurgia textual: se rodou sem erro, a pagina nasce completa."""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ferramentas"))

TPL = os.path.join(ROOT, "ferramentas", "template_base.html")
IDX = os.path.join(ROOT, "index.html")
REG = os.path.join(ROOT, "produtos.json")

DIV_RE = re.compile(r"<div\b|</div>")

CSS_EXTRA = """    .card-img {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    .cats {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: center;
      padding: 0 20px 28px;
    }
    .cat-btn {
      background: rgba(255,255,255,0.06);
      color: #f8fafc;
      border: 1px solid rgba(255,255,255,0.15);
      padding: 9px 18px;
      border-radius: 999px;
      cursor: pointer;
      font-family: inherit;
      font-size: 0.92rem;
      font-weight: 700;
      transition: all 0.2s;
    }
    .cat-btn:hover { border-color: #ee4d2d; }
    .cat-btn.active {
      background: #ee4d2d;
      border-color: #ee4d2d;
      color: #fff;
    }
"""

FILTRO_JS = """<script>
(function(){
function aplicarFiltros(){
var termo=(document.getElementById('searchInput')?document.getElementById('searchInput').value:'').toLowerCase().trim();
var ativa=document.querySelector('.cat-btn.active');
var cat=ativa?ativa.getAttribute('data-cat'):'todos';
document.querySelectorAll('#productGrid .card').forEach(function(c){
var txt=((c.querySelector('.card-title')||{textContent:''}).textContent||'')+' '+((c.querySelector('.card-desc')||{textContent:''}).textContent||'');
var okCat=(cat==='todos'||c.getAttribute('data-categoria')===cat);
var okBusca=!termo||txt.toLowerCase().indexOf(termo)!==-1;
c.style.display=(okCat&&okBusca)?'':'none';
});
}
window.filterItems=aplicarFiltros;
var si=document.getElementById('searchInput');
if(si){si.addEventListener('keyup',aplicarFiltros);si.addEventListener('input',aplicarFiltros);}
var bs=document.querySelectorAll('.cat-btn');
bs.forEach(function(b){b.addEventListener('click',function(){
bs.forEach(function(x){x.classList.remove('active');});
b.classList.add('active');
aplicarFiltros();
});});
})();
</script>"""


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def grid_span(html, start):
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


def make_card(num, rel, url, titulo, categoria):
    badges = [
        ("badge-hot", "Destaque"),
        ("badge-toprated", "Mais Vendido"),
        ("badge-shipping", "Frete Grátis"),
    ]
    bcls, btxt = badges[(num - 1) % len(badges)]
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



SEO_TITLE = 'Ofertas Shopee - Ferramentas, Automotivo e Mobilidade Elétrica | Achadinhos'
SEO_DESC = 'As melhores ofertas da Shopee com frete grátis: ferramentas profissionais, acessórios automotivos e de moto, mobilidade elétrica e eletrônicos. Preços imbatíveis direto dos fornecedores!'
SEO_URL = 'https://aalexaalmeida108-cmd.github.io/loja/'
SEO_IMG = 'https://aalexaalmeida108-cmd.github.io/loja/img/produto_03.jpg'


def aplicar_seo(tpl):
    bloco = (
        "<title>" + SEO_TITLE + "</title>\n"
        '    <meta name="description" content="' + SEO_DESC + '">\n'
        '    <meta name="robots" content="index, follow">\n'
        '    <link rel="canonical" href="' + SEO_URL + '">\n'
        '    <meta property="og:type" content="website">\n'
        '    <meta property="og:site_name" content="Achadinhos Shopee">\n'
        '    <meta property="og:title" content="' + SEO_TITLE + '">\n'
        '    <meta property="og:description" content="' + SEO_DESC + '">\n'
        '    <meta property="og:image" content="' + SEO_IMG + '">\n'
        '    <meta property="og:url" content="' + SEO_URL + '">\n'
        '    <meta name="twitter:card" content="summary_large_image">\n'
        '    <meta name="twitter:title" content="' + SEO_TITLE + '">\n'
        '    <meta name="twitter:description" content="' + SEO_DESC + '">\n'
        '    <meta name="twitter:image" content="' + SEO_IMG + '">'
    )
    return re.sub(r"<title>.*?</title>", bloco, tpl, count=1, flags=re.S)




GSC_META = "<meta name=\"google-site-verification\" content=\"gqn4su5kU4SzdRJQc886KAFFLqaYM7p4kXiX_iglPKo\">"

def gerar(reg=None):
    if reg is None:
        try:
            reg = json.load(open(REG, encoding="utf-8"))
        except Exception:
            reg = []

    for r in reg:
        if not r.get("categoria"):
            r["categoria"] = "Outros"

    visiveis = [
        r
        for r in sorted(reg, key=lambda x: x["num"])
        if r.get("img_path") and os.path.exists(os.path.join(ROOT, r["img_path"]))
    ]

    cats = []
    for r in visiveis:
        c = r.get("categoria", "Outros")
        if c not in cats:
            cats.append(c)

    botoes = ['<button class="cat-btn active" data-cat="todos">Todos</button>']
    for c in sorted(cats):
        botoes.append(
            f'<button class="cat-btn" data-cat="{esc(c)}">{esc(c)}</button>'
        )
    pills = (
        '<div class="cats" id="catMenu">\n'
        + "\n".join("        " + b for b in botoes)
        + "\n      </div>"
    )

    cards = []
    usadas = set()
    for r in visiveis:
        rel = "img/" + os.path.basename(r["img_path"])
        usadas.add(os.path.basename(r["img_path"]))
        cards.append(
            make_card(r["num"], rel, r["url"], r.get("title", ""), r["categoria"])
        )

    for f in glob.glob(os.path.join(ROOT, "img", "*")):
        if os.path.basename(f) not in usadas:
            os.remove(f)

    tpl = open(TPL, encoding="utf-8").read()
    tpl = re.sub(r"<script>.*?</script>", "", tpl, flags=re.S)
    tpl = aplicar_seo(tpl)
    tpl = tpl.replace("</style>", CSS_EXTRA + "  </style>", 1)

    g0 = tpl.find('<div class="grid" id="productGrid">')
    g_end = grid_span(tpl, g0)
    body_start = tpl.find(">", g0) + 1

    close_start = tpl.rfind("</div>", body_start, g_end)
    new_html = (
        tpl[:body_start]
        + "\n"
        + "\n".join(cards)
        + "\n      "
        + tpl[close_start:].lstrip()
    )
    new_html = new_html.replace(
        '<div class="grid" id="productGrid">',
        pills + '\n      <div class="grid" id="productGrid">',
        1,
    )
    new_html = new_html.replace("</body>", FILTRO_JS + "\n</body>", 1)
    new_html = new_html.replace("<title>", GSC_META + "\n    <title>", 1)

    with open(IDX, "w", encoding="utf-8") as f:
        f.write(new_html)

    sem_com = re.sub(r"<!--.*?-->", "", new_html, flags=re.S)
    abertas = len(re.findall(r"<div\b", sem_com))
    fechadas = sem_com.count("</div>")
    ok = (
        abertas == fechadas
        and "<script" in new_html
        and "aplicarFiltros" in new_html
        and 'id="catMenu"' in new_html
        and "</html>" in new_html
    )
    print(
        f"gerada: {len(cards)} cards | {len(cats)} categorias | "
        f"divs {abertas}/{fechadas} | {'OK' if ok else 'ERRO'}"
    )
    return ok


if __name__ == "__main__":
    ok = gerar()
    sys.exit(0 if ok else 1)
