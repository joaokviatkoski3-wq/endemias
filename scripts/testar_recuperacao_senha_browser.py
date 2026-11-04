"""Percurso real de navegador em copia sintetica local, com CSRF habilitado."""

import json
import os
from pathlib import Path
import shutil
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if ROOT == Path(r"C:\endemias"):
        raise ValueError("Teste somente em worktree separada.")
    runtime = ROOT / ".venv/browser-recuperacao"
    runtime.mkdir(exist_ok=True)
    database = runtime / "sintetico.db"
    if database.exists():
        raise ValueError("Exige copia sintetica nova.")
    seed = ROOT / ".venv/recuperacao-seed.db"
    shutil.copyfile(seed, database)
    os.environ.update(ENDEMIAS_DB_BACKEND="sqlite", ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime), ENDEMIAS_LOG_PATH=str(runtime / "browser.log"),
        ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK="1")
    from app import create_app
    from playwright.sync_api import sync_playwright
    from waitress import create_server
    application = create_app({"REQUIRE_SESSION_TOKEN": True})
    server = create_server(application, host="127.0.0.1", port=5004, threads=4)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    stage = "login"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            admin = browser.new_context()
            user = browser.new_context()
            reset = browser.new_context(viewport={"width": 390, "height": 844})
            a, u, r = admin.new_page(), user.new_page(), reset.new_page()
            errors, request_urls = [], []
            for page in (a, u, r):
                page.on("pageerror", lambda error: errors.append(type(error).__name__))
                page.on("request", lambda req: request_urls.append(req.url))
            base = "http://127.0.0.1:5004"
            for page, username in ((a, "admin"), (u, "ficticio3")):
                page.goto(base + "/login")
                page.locator('[name="usuario"]').fill(username)
                page.locator('[name="senha"]').fill("SenhaSomenteDeTeste123!")
                page.get_by_role("button", name="Entrar", exact=True).click()
                page.wait_for_url(base + "/")
            stage = "gerar_link"
            a.goto(base + "/admin/usuarios")
            a.on("dialog", lambda dialog: dialog.accept())
            row = a.locator("tr").filter(has_text="ficticio3")
            row.get_by_role("button", name="Gerar link de recuperação").click()
            a.locator("#modal-recuperacao").wait_for(state="visible")
            link = a.locator("#recuperacao-url").input_value()
            token = link.split("#", 1)[1]
            assert link.startswith("https://endemias.vsatt.com.br/recuperar-senha#")
            stage = "nova_senha"
            r.goto(base + "/recuperar-senha#" + token)
            r.locator("#recuperar-form").wait_for(state="visible")
            assert r.url == base + "/recuperar-senha"
            assert r.evaluate("document.documentElement.scrollWidth <= innerWidth")
            r.screenshot(path=str(runtime / "recuperar-celular.png"), full_page=True)
            r.locator("#nova").fill("NovaSenhaFicticiaDoBrowser!")
            r.locator("#confirmar").fill("DiferenteSenhaFicticia!")
            r.get_by_role("button", name="Salvar nova senha").click()
            r.get_by_role("alert").filter(has_text="As senhas não coincidem").wait_for()
            r.locator("#nova").fill("NovaSenhaFicticiaDoBrowser!")
            r.locator("#confirmar").fill("NovaSenhaFicticiaDoBrowser!")
            r.get_by_role("button", name="Salvar nova senha").click()
            r.get_by_role("status").filter(has_text="Senha alterada com sucesso").wait_for()
            stage = "sessao_revogada"
            u.goto(base + "/api/formularios")
            u.wait_for_url("**/login?next=**")
            r.get_by_role("link", name="Voltar para entrar no sistema").click()
            r.locator('[name="usuario"]').fill("ficticio3")
            r.locator('[name="senha"]').fill("NovaSenhaFicticiaDoBrowser!")
            r.get_by_role("button", name="Entrar", exact=True).click()
            r.wait_for_url(base + "/")
            stage = "uso_unico"
            r.goto(base + "/recuperar-senha#" + token)
            r.locator("#nova").fill("OutraSenhaFicticiaDoBrowser!")
            r.locator("#confirmar").fill("OutraSenhaFicticiaDoBrowser!")
            r.get_by_role("button", name="Salvar nova senha").click()
            r.get_by_role("alert").filter(has_text="já utilizado").wait_for()
            assert not any(token in url for url in request_urls)
            assert not errors
            token, link = None, None
            browser.close()
        result = {"ok": True, "csrf_real": True, "mobile": True, "sessao_anterior_revogada": True,
                  "uso_unico": True, "token_ausente_urls_http": True, "javascript_errors": 0}
    except Exception as error:
        # Nao exportar traceback de fill(), URL ou token de recuperacao.
        result = {"ok": False, "stage": stage, "error_type": type(error).__name__}
    finally:
        server.close()
        server.task_dispatcher.shutdown()
        thread.join(timeout=5)
    (runtime / "resultado.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
