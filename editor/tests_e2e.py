"""Testes de ponta a ponta num navegador de verdade.

Rodam só no job `e2e` do CI (`pytest -m e2e`) e ficam de fora da suíte comum,
que não tem Playwright instalado. Para rodar na mão:

    pip install pytest-playwright && playwright install chromium
    pytest -m e2e

O que estes testes cobrem e os outros não: que a página chega ao navegador
inteira, com CSS e JS de verdade. Vale mais aqui do que num CRUD comum porque
o editor de template (`template_detail.html`) é montado em cima de um canvas
fabric.js — um `assertContains` do test client não prova que o canvas montou
sem lançar exceção, só que o HTML/JS chegaram no `<script>`.

Deliberadamente poucos. Suíte e2e grande envelhece mal, e a primeira falha
intermitente ensina a equipe a ignorar o vermelho.
"""

from pathlib import Path

import pytest
from reportlab.pdfgen import canvas


def _build_pdf_on_disk(tmp_path: Path) -> Path:
    caminho = tmp_path / "fundo.pdf"
    pdf_canvas = canvas.Canvas(str(caminho), pagesize=(400, 120))
    pdf_canvas.drawString(24, 100, "Fundo de teste")
    pdf_canvas.showPage()
    pdf_canvas.save()
    return caminho


@pytest.fixture
def usuario_e2e(django_user_model):
    from core.testing import SENHA_TESTE

    return django_user_model.objects.create_user(username="e2e-editor", password=SENHA_TESTE)


def _logar(page, live_server, usuario_e2e):
    from core.testing import SENHA_TESTE

    page.goto(f"{live_server.url}/login/")
    page.locator("#id_username").fill(usuario_e2e.username)
    page.locator("#id_password").fill(SENHA_TESTE)
    page.locator('button[type="submit"]').first.click()


@pytest.mark.e2e
def test_login_leva_a_lista_de_templates(live_server, page, usuario_e2e):
    """A raiz do app redireciona para a lista de templates — é o `HomeView`."""
    _logar(page, live_server, usuario_e2e)

    page.wait_for_url(f"{live_server.url}/templates/")
    assert page.locator("h1, .hero-title").first.is_visible()


@pytest.mark.e2e
def test_pagina_sem_sessao_redireciona_para_login(page, live_server):
    """`LoginRequiredMixin` de verdade, testado como o navegador vê: via redirect HTTP."""
    resposta = page.goto(f"{live_server.url}/templates/")

    assert resposta.url.startswith(f"{live_server.url}/login/")


@pytest.mark.e2e
def test_criar_template_com_fundo_e_abrir_o_editor_sem_erro_de_js(
    live_server, page, usuario_e2e, tmp_path
):
    """Fluxo completo: logar, criar um template com fundo em PDF, e abrir o
    editor de layout — a tela que monta um canvas fabric.js em cima do fundo.

    O canvas é onde um erro de JS realmente importa: sem ele montar, a pessoa
    não consegue posicionar nenhum campo no template.
    """
    erros_js = []
    page.on("pageerror", lambda exc: erros_js.append(str(exc)))

    _logar(page, live_server, usuario_e2e)
    page.wait_for_url(f"{live_server.url}/templates/")

    page.goto(f"{live_server.url}/templates/novo/")
    page.locator("#id_name").fill("Certificado E2E")
    fundo = _build_pdf_on_disk(tmp_path)
    page.locator("#id_background_pdf").set_input_files(str(fundo))
    page.locator('#template-form button[type="submit"]').click()

    page.wait_for_url(lambda url: "/templates/novo/" not in url, timeout=10_000)
    page.wait_for_load_state("networkidle")

    assert not erros_js, f"JavaScript quebrou ao abrir o editor: {erros_js}"

    from editor.models import DocumentTemplate

    assert DocumentTemplate.objects.filter(user=usuario_e2e, name="Certificado E2E").exists()
