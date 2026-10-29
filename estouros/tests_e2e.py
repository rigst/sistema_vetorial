"""Página de estouros no navegador: envio, processamento e download."""

import pikepdf
import pytest

from estouros.tests import criar_pdf


@pytest.fixture
def usuario_e2e(django_user_model):
    from core.testing import SENHA_TESTE

    return django_user_model.objects.create_user(username="e2e-estouro", password=SENHA_TESTE)


def _logar(page, live_server, usuario):
    from core.testing import SENHA_TESTE

    page.goto(f"{live_server.url}/login/")
    page.locator("#id_username").fill(usuario.username)
    page.locator("#id_password").fill(SENHA_TESTE)
    page.locator('button[type="submit"]').first.click()


@pytest.mark.e2e
def test_envia_configura_e_baixa_o_pdf_com_estouro(
    live_server, page, usuario_e2e, tmp_path, settings
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    pdf = criar_pdf(tmp_path / "Testeira.pdf")
    erros = []
    page.on("pageerror", lambda exc: erros.append(str(exc)))
    _logar(page, live_server, usuario_e2e)
    page.goto(f"{live_server.url}/estouros/")

    # Só os campos do modo escolhido aparecem.
    assert page.locator('[data-modo="igual"]').is_visible()
    assert not page.locator('[data-modo="lados"]').is_visible()
    page.get_by_text("Um valor por lado").click()
    assert page.locator('[data-modo="lados"]').is_visible()
    page.locator("#id_topo").fill("1")
    page.locator("#id_direita").fill("2")
    page.locator("#id_base").fill("1")
    page.locator("#id_esquerda").fill("2")
    assert (
        "topo 1, direita 2, base 1, esquerda 2 cm"
        in page.locator("[data-resumo-texto]").inner_text()
    )

    # A cor só aparece no modo cor sólida.
    assert not page.locator("[data-so-cor]").is_visible()
    page.get_by_text("Cor sólida", exact=True).click()
    assert page.locator("[data-so-cor]").is_visible()

    page.locator("#id_arquivos").set_input_files(str(pdf))
    assert "Testeira.pdf" in page.locator("[data-lista-envio]").inner_text()
    page.locator("[data-enviar]").click()

    page.wait_for_selector("text=Baixar", timeout=15000)
    assert "Concluído" in page.locator("[data-lote-status]").inner_text()
    # A prévia carrega depois da página: espera a imagem decodificar.
    previa = page.locator(".estouro-arquivo-previa img")
    previa.wait_for(state="visible", timeout=10000)
    page.wait_for_function(
        "img => img.complete && img.naturalWidth > 0", arg=previa.element_handle(), timeout=10000
    )
    with page.expect_download() as baixa:
        page.locator(".estouro-arquivo .button").first.click()
    arquivo = baixa.value
    assert arquivo.suggested_filename == "Testeira_estouro-1-2-1-2cm.pdf"
    destino = tmp_path / "baixado.pdf"
    arquivo.save_as(destino)
    with pikepdf.open(destino) as baixado:
        assert [float(v) for v in baixado.pages[0].obj.TrimBox] == [0, 0, 400, 200]
    assert erros == []


@pytest.mark.e2e
def test_pagina_nao_estoura_a_largura_no_celular(live_server, page, usuario_e2e):
    page.set_viewport_size({"width": 390, "height": 860})
    _logar(page, live_server, usuario_e2e)
    page.goto(f"{live_server.url}/estouros/")
    for modo in ("Igual nos 4 lados", "Horizontal e vertical", "Um valor por lado"):
        page.get_by_text(modo).click()
        assert page.evaluate("document.documentElement.scrollWidth") <= 390, modo
