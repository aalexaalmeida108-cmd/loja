#!/usr/bin/env python3
"""Coleta maiores altas da bolsa B3 + screenshots e envia ao Telegram."""
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126 Safari/537.36")

TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

OUT_DIR = Path("bolsa_out")
OUT_DIR.mkdir(exist_ok=True)

SITES = {
    "investing": "https://br.investing.com/equities/brazil",
    "yahoo": "https://finance.yahoo.com/most-active?count=100",
}


def tg_send_text(text):
    if not TOKEN or not CHAT_ID:
        print("sem TELEGRAM_TOKEN/CHAT_ID, pulando envio")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "disable_web_page_preview": True},
            timeout=60,
        )
    except Exception as e:
        print("erro sendMessage:", e)


def tg_send_photo(path, caption=""):
    if not TOKEN or not CHAT_ID:
        print("sem token, sem foto")
        return
    try:
        with open(path, "rb") as f:
            requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendPhoto",
                data={"chat_id": CHAT_ID, "caption": caption[:1000]},
                files={"photo": f},
                timeout=90,
            )
    except Exception as e:
        print("erro sendPhoto:", e)


def extrai_tabelas(page):
    return page.evaluate("""() => {
        const tables = document.querySelectorAll('table');
        const results = [];
        tables.forEach((table, i) => {
            const rows = table.querySelectorAll('tr');
            if (rows.length < 3) return;
            const headers = Array.from(rows[0].querySelectorAll('th, td')).map(c => c.innerText.trim());
            const dataRows = [];
            for (let r = 1; r < Math.min(rows.length, 31); r++) {
                const cells = Array.from(rows[r].querySelectorAll('td, th')).map(c => c.innerText.trim());
                if (cells.some(c => c)) dataRows.push(cells);
            }
            if (dataRows.length > 0) results.push({tableIndex: i, headers, rows: dataRows});
        });
        return results;
    }""")


def roda_investing(page):
    print("[investing] navegando...")
    page.goto(SITES["investing"], wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    for sel in ['[data-test="popup-close"]', '.popupCloseIcon',
                'button:has-text("Agora não")', 'button:has-text("Fechar")',
                '.onetrust-close-btn-handler']:
        try:
            page.click(sel, timeout=2000)
        except Exception:
            pass
    for _ in range(3):
        page.mouse.wheel(0, 2000)
        page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT_DIR / "investing_full.png"), full_page=True)
    return extrai_tabelas(page)


def roda_yahoo(page):
    print("[yahoo] navegando...")
    try:
        page.goto(SITES["yahoo"], wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        for _ in range(3):
            page.mouse.wheel(0, 2000)
            page.wait_for_timeout(1500)
        try:
            page.locator("section table").first.screenshot(path=str(OUT_DIR / "yahoo_table.png"))
        except Exception:
            page.screenshot(path=str(OUT_DIR / "yahoo_full.png"), full_page=True)
        return extrai_tabelas(page)
    except Exception as e:
        print("yahoo erro:", e)
        return []


def monta_relatorio(dados_investing, dados_yahoo):
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y %H:%M")
    linhas = [f"📈 Maiores Altas da Bolsa - {agora}", "Fonte: Investing.com (Brasil)", ""]

    for t in dados_investing:
        if t["tableIndex"] == 2 and "Var. %" in str(t["headers"]):
            linhas.append("🚀 Top Maiores Altas (Investing)")
            linhas.append("| # | Ativo | Último | Var% | Vol |")
            linhas.append("|---|-------|--------|------|-----|")
            for i, row in enumerate(t["rows"][:12], 1):
                if len(row) >= 4:
                    linhas.append(f"| {i} | {row[0]} | {row[1]} | {row[2]} | {row[3]} |")
            linhas.append("")
        # tabela principal (todas ações) filtrada por positivas relevantes
        if t["tableIndex"] == 0 and "Var. %" in str(t["headers"]):
            pos = [r for r in t["rows"] if len(r) > 6 and r[6].startswith("+")]
            if pos:
                linhas.append("📊 Altas no Pregão (principais ações)")
                linhas.append("| Ativo | Último | Var% | Vol |")
                linhas.append("|-------|--------|------|-----|")
                for row in pos[:10]:
                    linhas.append(f"| {row[1]} | {row[2]} | {row[6]} | {row[7]} |")
                linhas.append("")

    for t in dados_yahoo:
        if "Change %" in str(t["headers"]):
            pos = [r for r in t["rows"] if len(r) > 5 and r[5].startswith("+")]
            if pos:
                linhas.append("🌍 Yahoo (mundial) top altas")
                linhas.append("| Símbolo | Nome | Preço | Var% |")
                linhas.append("|---------|------|-------|------|")
                for row in pos[:8]:
                    linhas.append(f"| {row[0]} | {row[1]} | {row[3]} | {row[5]} |")
                linhas.append("")

    linhas.append("---")
    linhas.append("Gerado automaticamente. Valores podem ter atraso.")
    texto = "\n".join(linhas)
    (OUT_DIR / "RELATORIO.md").write_text(texto, encoding="utf-8")
    return texto


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--disable-gpu"],
        )
        ctx = browser.new_context(user_agent=UA, viewport={"width": 1920, "height": 1080})
        page = ctx.new_page()

        try:
            dados_inv = roda_investing(page)
        except Exception as e:
            print("investing erro geral:", e)
            dados_inv = []
        try:
            dados_yah = roda_yahoo(page)
        except Exception:
            dados_yah = []

        browser.close()

    rel = monta_relatorio(dados_inv, dados_yah)
    print(rel)

    if not rel.strip() or rel.strip().startswith("📈 Maiores Altas") and "Top" not in rel:
        pass

    tg_send_text(rel)
    for im in ["investing_full.png", "yahoo_table.png", "yahoo_full.png"]:
        fp = OUT_DIR / im
        if fp.exists():
            tg_send_photo(str(fp), im)


if __name__ == "__main__":
    main()
