"""Navegador descartavel no piloto HTTPS, sem usar o perfil pessoal."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://piloto.vsatt.com.br"


def main():
    from playwright.sync_api import sync_playwright
    runtime = ROOT / ".venv/piloto-web"
    if json.loads((runtime / "massa.json").read_text()).get("sintetico") is not True:
        raise ValueError("Exige piloto ficticio.")
    secret = next(line.split(":", 1)[1].strip() for line in (runtime / "acesso.local.txt").read_text().splitlines() if line.startswith("Senha:"))
    stage = "login"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(BASE + "/login")
            page.locator("[name=usuario]").fill("ficticio3")
            page.locator("[name=senha]").fill(secret)
            page.get_by_role("button", name="Entrar", exact=True).click()
            page.wait_for_url(BASE + "/")
            secret = None
            stage = "rg_online"
            page.goto(BASE + "/formularios/rg-campo")
            page.evaluate("navigator.serviceWorker.ready")
            page.wait_for_function("navigator.serviceWorker.controller !== null")
            page.wait_for_function("async () => !!(await caches.match('/formularios/rg-campo'))")
            page.screenshot(path=str(ROOT / ".venv/piloto-publico-desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.screenshot(path=str(ROOT / ".venv/piloto-publico-celular.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            stage = "rg_offline"
            context.set_offline(True)
            page.reload()
            page.wait_for_selector("#rgc-grid", state="attached")
            assert page.locator("h1").inner_text().startswith("Atualização de RG")
            assert not errors
            context.set_offline(False)
            stage = "logout_limpa_cache"
            page.goto(BASE + "/termos")
            page.get_by_role("button", name="Sair sem aceitar").click()
            page.wait_for_url("**/login")
            assert page.evaluate("async () => !(await caches.match('/formularios/rg-campo'))")
            browser.close()
        result = {"ok": True, "desktop_mobile": True, "rg_offline_https": True, "logout_cache_limpo": True, "javascript_errors": 0}
    except Exception as error:
        # Excecoes do Playwright podem incluir o valor de fill(); nao exportar.
        result = {"ok": False, "stage": stage, "error_type": type(error).__name__}
    (ROOT / ".venv/piloto-publico-browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
