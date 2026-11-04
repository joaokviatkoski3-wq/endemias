"""Navegador e SQLite ficticios, com CSRF real e relogio de presenca controlado."""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if ROOT == Path(r"C:\endemias"):
        raise ValueError("Teste somente em worktree separada.")
    runtime = Path(tempfile.mkdtemp(prefix="browser-presenca-", dir=ROOT / ".venv"))
    database = runtime / "sintetico.db"
    shutil.copyfile(ROOT / ".venv/presenca-seed.db", database)
    os.environ.update(ENDEMIAS_DB_BACKEND="sqlite", ENDEMIAS_DB_PATH=str(database),
        ENDEMIAS_INSTANCE_DIR=str(runtime), ENDEMIAS_LOG_PATH=str(runtime / "browser.log"),
        ENDEMIAS_TEST_BLOCK_CONTAOVOS_NETWORK="1")
    from app import create_app
    from app_core import presenca, db
    from playwright.sync_api import sync_playwright
    from waitress import create_server
    application = create_app({"REQUIRE_SESSION_TOKEN": True})
    server = create_server(application, host="127.0.0.1", port=5005, threads=4)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    stage = "login"
    clock = [int(time.time())]
    try:
        with patch.object(presenca, "time", SimpleNamespace(time=lambda: clock[0])), sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            admin = browser.new_context(viewport={"width": 1440, "height": 1000})
            device1, device2 = browser.new_context(), browser.new_context()
            a, u, v = admin.new_page(), device1.new_page(), device2.new_page()
            errors = []
            for page in (a, u, v):
                page.on("pageerror", lambda error: errors.append(type(error).__name__))
            base = "http://127.0.0.1:5005"
            for page, username in ((a, "admin"), (u, "ficticio3"), (v, "ficticio3")):
                page.goto(base + "/login")
                page.locator('[name="usuario"]').fill(username)
                page.locator('[name="senha"]').fill("SenhaSomenteDeTeste123!")
                with page.expect_response(lambda r: r.url.endswith('/api/presenca')) as signal:
                    page.get_by_role("button", name="Entrar", exact=True).click()
                assert signal.value.status == 200
                assert "set-cookie" not in signal.value.headers
            stage = "resumo"
            a.goto(base + "/admin/usuarios")
            a.locator("#row-3 [data-presenca-status]").filter(has_text="Online").wait_for()
            a.locator("#presenca-resumo").filter(has_text="2 usuários online").wait_for()
            a.locator("#row-2 [data-presenca-ultima]").filter(has_text="Sem registro").wait_for()
            assert a.locator("#row-3 [data-presenca-ultima]").inner_text() == "Agora"
            # Outra aba do mesmo navegador nao cria uma terceira sessao.
            tab = device2.new_page()
            with tab.expect_response(lambda r: r.url.endswith('/api/presenca')):
                tab.goto(base + "/minha-senha")
            conn = db.connect(database)
            try:
                assert conn.execute("SELECT COUNT(*) FROM usuarios_presenca_sessoes WHERE usuario_id=3").fetchone()[0] == 2
            finally:
                conn.close()
            stage = "abrir_menu_logout"
            u.locator('#userMenuToggle').click()
            stage = "clicar_sair"
            u.locator('#user-menu').get_by_role('button', name='Sair', exact=True).click()
            stage = "confirmar_logout"
            u.wait_for_url(base + "/login")
            stage = "resumo_apos_logout"
            a.evaluate("window.dispatchEvent(new Event('endemias:presenca-confirmada'))")
            a.locator("#row-3 [data-presenca-status]").filter(has_text="Online").wait_for()
            # Ao ocultar a pagina, o temporizador nao envia sinais.
            tab.close()
            v.clock.install()
            v.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=> 'hidden'}); document.dispatchEvent(new Event('visibilitychange'))")
            beats = []
            v.on('request', lambda req: beats.append(req.url) if req.url.endswith('/api/presenca') else None)
            v.clock.fast_forward(90000)
            assert not beats
            stage = "expiracao"
            clock[0] += 121
            a.evaluate("window.dispatchEvent(new Event('endemias:presenca-confirmada'))")
            a.locator("#row-3 [data-presenca-status]").filter(has_text="Offline").wait_for()
            assert "Hoje" in a.locator("#row-3 [data-presenca-ultima]").inner_text()
            # Retomar a pagina envia sinal imediatamente.
            with v.expect_response(lambda r: r.url.endswith('/api/presenca')):
                v.evaluate("Object.defineProperty(document, 'visibilityState', {configurable:true, get:()=> 'visible'}); document.dispatchEvent(new Event('visibilitychange'))")
            a.evaluate("window.dispatchEvent(new Event('endemias:presenca-confirmada'))")
            a.locator("#row-3 [data-presenca-status]").filter(has_text="Online").wait_for()
            # Data de ontem em Brasilia e exibida pelo cliente sem depender do fuso do PC.
            conn = db.connect(database)
            try:
                conn.execute("INSERT INTO usuarios_presenca(usuario_id,ultima_presenca) VALUES (2,?)", (clock[0] - 86400,))
                conn.commit()
            finally:
                conn.close()
            a.evaluate("window.dispatchEvent(new Event('endemias:presenca-confirmada'))")
            a.locator("#row-2 [data-presenca-ultima]").filter(has_text="Ontem").wait_for()
            stage = "layout"
            a.screenshot(path=str(runtime / "usuarios-desktop.png"), full_page=True)
            a.set_viewport_size({"width": 390, "height": 844})
            assert a.evaluate("document.documentElement.scrollWidth <= innerWidth")
            a.screenshot(path=str(runtime / "usuarios-celular.png"), full_page=True)
            assert not errors
            browser.close()
        result = {"ok": True, "varios_aparelhos_abas": True, "logout_parcial": True,
            "expiracao_retorno_visibilidade": True, "datas_brasilia": True,
            "csrf_real": True, "cookie_sem_renovacao_por_polling": True,
            "mobile_sem_overflow": True, "javascript_errors": 0, "artefatos": str(runtime)}
    except Exception as error:
        # Erros Playwright podem conter valores de formularios; nao exportar.
        result = {"ok": False, "stage": stage, "error_type": type(error).__name__, "artefatos": str(runtime)}
        try:
            u.screenshot(path=str(runtime / "falha-usuario.png"), full_page=True)
            result["javascript_errors"] = len(errors)
        except Exception:
            pass
    finally:
        server.close()
        server.task_dispatcher.shutdown()
        thread.join(timeout=5)
    (ROOT / ".venv/browser-presenca-resultado.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
