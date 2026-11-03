"""QA opcional em navegador de ensaio; requer Playwright, nao altera producao."""

import sys
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.preparar_massa_web_teste import preparar


def main():
    from playwright.sync_api import sync_playwright
    from waitress import create_server
    path = ROOT / ".venv" / ("interface-" + uuid.uuid4().hex + ".db")
    preparar(path)
    from app import create_app
    app = create_app({"DB_PATH": str(path), "TERMOS_USO_ENABLED": True})
    server = create_server(app, host="127.0.0.1", port=0, threads=8)
    threading.Thread(target=server.run, daemon=True).start()
    base = "http://127.0.0.1:" + str(server.effective_port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def login():
                page.goto(base + "/login")
                page.locator("[name=usuario]").fill("admin")
                page.locator("[name=senha]").fill("SenhaSomenteDeTeste123!")
                page.get_by_role("button", name="Entrar", exact=True).click()

            login()
            page.wait_for_url("**/termos")
            assert not page.locator("[name=concordo]").is_checked()
            page.screenshot(path=str(ROOT / ".venv/termo-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(ROOT / ".venv/termo-celular.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.locator("[name=concordo]").check()
            page.get_by_role("button", name="Confirmar e acessar o sistema").click()
            page.wait_for_url(base + "/")
            page.goto(base + "/formularios/rg-campo")
            page.evaluate("navigator.serviceWorker.ready")
            page.wait_for_function("navigator.serviceWorker.controller !== null")
            page.wait_for_function("async () => !!(await caches.match('/formularios/rg-campo'))")
            context.set_offline(True)
            page.reload()
            page.wait_for_selector("#rgc-grid", state="attached")
            assert page.locator("h1").inner_text().startswith("Atualização de RG")
            assert not errors, errors
            context.set_offline(False)
            page.goto(base + "/termos")
            page.get_by_role("button", name="Sair sem aceitar").click()
            page.wait_for_url("**/login")
            assert page.evaluate("async () => !(await caches.match('/formularios/rg-campo'))")
            login()
            page.wait_for_url(base + "/")
            browser.close()
        print("OK navegador: termo desktop/celular, aceite persistido, RG offline sem erros JS, logout e novo login.")
    finally:
        server.close()
        server.task_dispatcher.shutdown()


if __name__ == "__main__":
    main()
