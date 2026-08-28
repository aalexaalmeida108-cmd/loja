#!/usr/bin/env python3
"""Proxy web via GitHub Actions: acessa qualquer URL e salva o texto extraído.
Uso: python proxy/busca_pagina.py <url> <saida>
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")


def extrair_texto(page, max_len=60000):
    page.wait_for_timeout(1500)
    # remove scripts/styles, pega o texto visível
    texto = page.evaluate("""() => {
        let el = document.body.cloneNode(true);
        el.querySelectorAll('script, style, noscript, svg, iframe').forEach(n => n.remove());
        return el.innerText || '';
    }""")
    texto = re.sub(r'\n{3,}', '\n\n', texto or '')
    return texto[:max_len]


def main():
    url = sys.argv[1]
    saida = Path(sys.argv[2])
    saida.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-gpu"],
        )
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        msg = ""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)
            titulo = page.title() or ""
            texto = extrair_texto(page)
            final_url = page.url
            msg = f"URL: {url}\nFinal: {final_url}\nTitulo: {titulo}\n\n{texto}"
        except Exception as e:
            msg = f"ERRO ao acessar {url}: {e}"
        finally:
            browser.close()

    saida.write_text(msg, encoding="utf-8")
    print("OK:", len(msg), "chars ->", saida)


if __name__ == "__main__":
    main()
