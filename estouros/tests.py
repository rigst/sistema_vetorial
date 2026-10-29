"""Estouros: fidelidade do PDF (o que a gráfica recebe) e a página web."""

from __future__ import annotations

import hashlib
import io
import shutil
import subprocess
import tempfile
import zipfile
import zlib
from pathlib import Path

import pikepdf
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageChops

from core.testing import SENHA_TESTE

from .forms import EstouroForm, sufixo_arquivo
from .models import ArquivoEstouro, LoteEstouro
from .pdf import (
    PT_POR_UNIDADE,
    Configuracao,
    ErroEstouro,
    Lados,
    aplicar_estouro,
    lados_no_espaco_da_pagina,
)
from .services import processar_lote

CM = PT_POR_UNIDADE["cm"]
TEST_MEDIA_ROOT = tempfile.mkdtemp(prefix="vetorial_estouros_tests_")


# ------------------------------------------------------------ PDFs de teste


def _imagem_rgb(pdf: pikepdf.Pdf, largura=64, altura=32) -> tuple[pikepdf.Stream, bytes]:
    """Imagem com gradiente, comprimida com nível 1 (diferente do padrão do
    qpdf): se alguém recomprimir, os bytes mudam e o teste pega."""
    pixels = bytes((x * 4) % 256 for _ in range(altura) for x in range(largura) for _ in range(3))
    bruto = zlib.compress(pixels, 1)
    imagem = pikepdf.Stream(
        pdf,
        bruto,
        Type=pikepdf.Name.XObject,
        Subtype=pikepdf.Name.Image,
        Width=largura,
        Height=altura,
        ColorSpace=pikepdf.Name.DeviceRGB,
        BitsPerComponent=8,
        Filter=pikepdf.Name.FlateDecode,
    )
    return imagem, bruto


def _desenho_teste(tamanho, n: int) -> bytes:
    w, h = tamanho
    return (
        f"0.1 0.3 0.8 rg 0 0 {w} {h} re f "
        f"q {w / 2} 0 0 {h / 2} 0 0 cm /Im0 Do Q "
        f"1 0 0 rg {w * 0.6} {h * 0.6} {w * 0.4} {h * 0.4} re f "
        f"0 g {n * 10 + 10} 10 20 20 re f"
    ).encode()


def criar_pdf(
    caminho: Path,
    *,
    tamanho=(400.0, 200.0),
    paginas=1,
    rotacao=0,
    user_unit=None,
    trimbox=None,
    cropbox=None,
    recursos_herdados=False,
    contents_em_array=False,
):
    """Página com fundo azul cheio, uma imagem e um traço — tudo encostando na
    borda, para o estouro ter o que espelhar."""
    pdf = pikepdf.Pdf.new()
    imagem, _ = _imagem_rgb(pdf)
    recursos = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Im0=imagem))
    for n in range(paginas):
        pagina = pdf.add_blank_page(page_size=tamanho)
        desenho = _desenho_teste(tamanho, n)
        if contents_em_array:
            meio = len(desenho) // 2
            corte = desenho.rfind(b" ", 0, meio)
            pagina.obj.Contents = pikepdf.Array(
                [pdf.make_stream(desenho[:corte]), pdf.make_stream(desenho[corte:])]
            )
        else:
            pagina.obj.Contents = pdf.make_stream(desenho)
        if not recursos_herdados:
            pagina.obj.Resources = recursos
        if rotacao:
            pagina.obj.Rotate = rotacao
        if user_unit:
            pagina.obj.UserUnit = user_unit
        if trimbox:
            pagina.obj.TrimBox = pikepdf.Array(trimbox)
        if cropbox:
            pagina.obj.CropBox = pikepdf.Array(cropbox)
    if recursos_herdados:
        pdf.Root.Pages.Resources = recursos
        for pagina in pdf.pages:
            if "/Resources" in pagina.obj:
                del pagina.obj["/Resources"]
    pdf.save(caminho, compress_streams=True)
    return caminho


def streams_raw(caminho: Path) -> set[str]:
    with pikepdf.open(caminho) as pdf:
        return {
            hashlib.sha256(o.read_raw_bytes()).hexdigest()
            for o in pdf.objects
            if isinstance(o, pikepdf.Stream)
        }


def imagens(caminho: Path) -> dict[str, tuple]:
    with pikepdf.open(caminho) as pdf:
        return {
            hashlib.sha256(o.read_raw_bytes()).hexdigest(): (
                int(o.Width),
                int(o.Height),
                str(o.get("/Filter")),
                str(o.get("/ColorSpace")),
                int(o.get("/BitsPerComponent")),
            )
            for o in pdf.objects
            if isinstance(o, pikepdf.Stream) and o.get("/Subtype") == "/Image"
        }


def caixas(caminho: Path, pagina=0) -> dict[str, list[float]]:
    with pikepdf.open(caminho) as pdf:
        obj = pdf.pages[pagina].obj
        return {
            k: [round(float(v), 3) for v in obj[k]]
            for k in ("/MediaBox", "/CropBox", "/TrimBox", "/BleedBox")
            if k in obj
        }


def renderizar(caminho: Path, dpi=72, pagina=1) -> Image.Image:
    prefixo = caminho.parent / f"{caminho.stem}-r{dpi}p{pagina}"
    subprocess.run(
        [
            "pdftoppm",
            "-r",
            str(dpi),
            "-png",
            "-singlefile",
            "-cropbox",
            "-f",
            str(pagina),
            "-l",
            str(pagina),
            str(caminho),
            str(prefixo),
        ],
        check=True,
        capture_output=True,
    )
    return Image.open(prefixo.parent / f"{prefixo.name}.png").convert("RGB")


def pixels_diferentes(a: Image.Image, b: Image.Image) -> int:
    assert a.size == b.size, (a.size, b.size)
    return sum(ImageChops.difference(a, b).convert("L").histogram()[3:])


class _ComPasta(SimpleTestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp(prefix="estouro-"))
        self.addCleanup(shutil.rmtree, self.pasta, True)

    def estourar(self, origem: Path, config: Configuracao, nome="saida.pdf") -> Path:
        saida = self.pasta / nome
        aplicar_estouro(origem, saida, config)
        return saida


# --------------------------------------------------------------- fidelidade


class FidelidadeTests(_ComPasta):
    """A promessa: só cresce a página. O que já existia sai com os mesmos bytes."""

    def test_todos_os_streams_originais_saem_byte_a_byte_em_todos_os_modos(self):
        origem = criar_pdf(self.pasta / "o.pdf")
        antes = streams_raw(origem)
        for modo in ("espelhar", "esticar", "cor", "branco"):
            with self.subTest(modo=modo):
                saida = self.estourar(
                    origem,
                    Configuracao(Lados(20, 20, 20, 20), preenchimento=modo, marcas_corte=True),
                    f"{modo}.pdf",
                )
                self.assertEqual(antes - streams_raw(saida), set())
                self.assertEqual(imagens(saida), imagens(origem))

    def test_arte_identica_pixel_a_pixel_na_area_original(self):
        # 36 pt = 1/2 pol: a 72 dpi o estouro é exatamente 36 px, sem
        # arredondamento entre a arte e a borda.
        origem = criar_pdf(self.pasta / "o.pdf")
        original = renderizar(origem)
        for modo in ("espelhar", "esticar", "cor", "branco"):
            with self.subTest(modo=modo):
                saida = self.estourar(
                    origem, Configuracao(Lados(36, 36, 36, 36), preenchimento=modo), f"{modo}.pdf"
                )
                img = renderizar(saida)
                self.assertEqual(img.size, (original.width + 72, original.height + 72))
                # Interior da arte (sem a linha de 1 px que encosta no estouro).
                miolo = img.crop((37, 37, 36 + original.width - 1, 36 + original.height - 1))
                ref = original.crop((1, 1, original.width - 1, original.height - 1))
                self.assertEqual(pixels_diferentes(miolo, ref), 0)

    def test_modo_branco_e_identico_ate_na_borda(self):
        origem = criar_pdf(self.pasta / "o.pdf")
        original = renderizar(origem)
        img = renderizar(self.estourar(origem, Configuracao(Lados(36, 36, 36, 36), "branco")))
        miolo = img.crop((36, 36, 36 + original.width, 36 + original.height))
        self.assertEqual(pixels_diferentes(miolo, original), 0)

    def test_caixas_da_grafica_corte_e_estouro(self):
        origem = criar_pdf(self.pasta / "o.pdf", tamanho=(400, 200))
        saida = self.estourar(origem, Configuracao(Lados.na_unidade("cm", 1, 2, 3, 4)))
        c = caixas(saida)
        self.assertEqual(c["/TrimBox"], [0, 0, 400, 200])
        esperado = [
            round(-4 * CM, 3),
            round(-3 * CM, 3),
            round(400 + 2 * CM, 3),
            round(200 + 1 * CM, 3),
        ]
        self.assertEqual(c["/BleedBox"], esperado)
        self.assertEqual(c["/MediaBox"], esperado)
        self.assertEqual(c["/CropBox"], esperado)

    def test_marcas_de_corte_aumentam_a_folha_sem_mudar_corte_e_estouro(self):
        origem = criar_pdf(self.pasta / "o.pdf")
        sem = caixas(self.estourar(origem, Configuracao(Lados(20, 20, 20, 20)), "sem.pdf"))
        com = caixas(
            self.estourar(origem, Configuracao(Lados(20, 20, 20, 20), marcas_corte=True), "com.pdf")
        )
        self.assertEqual(sem["/TrimBox"], com["/TrimBox"])
        self.assertEqual(sem["/BleedBox"], com["/BleedBox"])
        self.assertLess(com["/MediaBox"][0], sem["/MediaBox"][0])

    def test_arquivo_cresce_pouco(self):
        origem = criar_pdf(self.pasta / "o.pdf")
        tamanho = origem.stat().st_size
        for modo in ("cor", "branco"):
            saida = self.estourar(origem, Configuracao(Lados(20, 20, 20, 20), modo), f"{modo}.pdf")
            self.assertLess(saida.stat().st_size - tamanho, 2048)


# ------------------------------------------------------------ casos de borda


class CasosDeBordaTests(_ComPasta):
    def test_cada_lado_com_seu_tamanho(self):
        origem = criar_pdf(self.pasta / "o.pdf")
        saida = self.estourar(origem, Configuracao(Lados(10, 20, 30, 40)))  # topo, dir, base, esq
        self.assertEqual(caixas(saida)["/BleedBox"], [-40, -30, 420, 210])

    def test_rotacao_aplica_os_lados_como_a_pagina_e_vista(self):
        lados = Lados(topo=10, direita=20, base=30, esquerda=40)
        # Com /Rotate 90 o lado esquerdo do espaço da página aparece em cima.
        self.assertEqual(lados_no_espaco_da_pagina(lados, 90), (10, 40, 30, 20))
        for rotacao in (0, 90, 180, 270):
            with self.subTest(rotacao=rotacao):
                origem = criar_pdf(self.pasta / f"r{rotacao}.pdf", rotacao=rotacao)
                saida = self.estourar(
                    origem, Configuracao(lados, "cor", cor=(1, 0, 0)), f"s{rotacao}.pdf"
                )
                img = renderizar(saida)
                original = renderizar(origem)
                # A imagem vista cresceu exatamente topo+base na altura e
                # esquerda+direita na largura, em qualquer rotação.
                self.assertEqual(img.size, (original.width + 60, original.height + 40))
                # E a faixa vermelha de 40 px está mesmo à esquerda visual.
                self.assertEqual(img.getpixel((5, img.height // 2)), (255, 0, 0))
                self.assertNotEqual(img.getpixel((45, img.height // 2)), (255, 0, 0))

    def test_user_unit_e_respeitado_na_conversao_de_cm(self):
        origem = criar_pdf(self.pasta / "o.pdf", tamanho=(100, 50), user_unit=10)
        saida = self.estourar(origem, Configuracao(Lados.na_unidade("cm", 2, 2, 2, 2)))
        bleed = caixas(saida)["/BleedBox"]
        # 2 cm = 56,69 pt reais = 5,669 unidades de 10 pt.
        self.assertAlmostEqual(bleed[0], -2 * CM / 10, places=3)
        with pikepdf.open(saida) as pdf:
            self.assertEqual(float(pdf.pages[0].obj.UserUnit), 10)

    def test_estouro_a_partir_da_linha_de_corte_existente(self):
        origem = criar_pdf(self.pasta / "o.pdf", trimbox=[10, 10, 390, 190])
        saida = self.estourar(origem, Configuracao(Lados(20, 20, 20, 20), referencia="corte"))
        c = caixas(saida)
        self.assertEqual(c["/TrimBox"], [10, 10, 390, 190])
        self.assertEqual(c["/BleedBox"], [-10, -10, 410, 210])

    def test_conteudo_fora_da_cropbox_nao_vaza_no_estouro(self):
        origem = criar_pdf(self.pasta / "o.pdf", cropbox=[50, 0, 400, 200])
        saida = self.estourar(origem, Configuracao(Lados(0, 0, 0, 36), "cor", cor=(0, 1, 0)))
        img = renderizar(saida)
        # A faixa à esquerda é a cor pedida, não a arte que existia antes do x=50.
        self.assertEqual(img.getpixel((10, 100)), (0, 255, 0))

    def test_recursos_herdados_e_varias_paginas(self):
        origem = criar_pdf(self.pasta / "o.pdf", paginas=3, recursos_herdados=True)
        saida = self.estourar(origem, Configuracao(Lados(20, 20, 20, 20)))
        with pikepdf.open(saida) as pdf:
            self.assertEqual(len(pdf.pages), 3)
            for pagina in pdf.pages:
                self.assertEqual([float(v) for v in pagina.obj.TrimBox], [0, 0, 400, 200])
        for n in (1, 3):
            self.assertEqual(renderizar(saida, pagina=n).size, (440, 240))

    def test_varios_content_streams(self):
        origem = criar_pdf(self.pasta / "o.pdf", contents_em_array=True)
        antes = streams_raw(origem)
        saida = self.estourar(origem, Configuracao(Lados(20, 20, 20, 20)))
        self.assertEqual(antes - streams_raw(saida), set())

    def test_espelhar_maior_que_a_arte_avisa_e_sugere_outro_modo(self):
        origem = criar_pdf(self.pasta / "o.pdf", tamanho=(100, 50))
        with self.assertRaisesMessage(ErroEstouro, "esticar"):
            self.estourar(origem, Configuracao(Lados(60, 0, 0, 0), "espelhar"))
        self.estourar(origem, Configuracao(Lados(60, 0, 0, 0), "esticar"), "ok.pdf")

    def test_arquivo_invalido_e_protegido(self):
        lixo = self.pasta / "lixo.pdf"
        lixo.write_bytes(b"%PDF-1.4 isto nao e um pdf")
        with self.assertRaisesMessage(ErroEstouro, "não é um PDF válido"):
            self.estourar(lixo, Configuracao(Lados(10, 10, 10, 10)))
        protegido = self.pasta / "senha.pdf"
        with pikepdf.Pdf.new() as pdf:
            pdf.add_blank_page()
            pdf.save(protegido, encryption=pikepdf.Encryption(user="x", owner="y"))
        with self.assertRaisesMessage(ErroEstouro, "senha"):
            self.estourar(protegido, Configuracao(Lados(10, 10, 10, 10)))

    def test_sem_estouro_e_sem_marcas_e_recusado(self):
        origem = criar_pdf(self.pasta / "o.pdf")
        with self.assertRaises(ErroEstouro):
            self.estourar(origem, Configuracao(Lados()))


# ------------------------------------------------------------------- web


def _upload(nome="testeira.pdf", **kw) -> SimpleUploadedFile:
    pasta = Path(tempfile.mkdtemp(prefix="estouro-up-"))
    caminho = criar_pdf(pasta / "x.pdf", **kw)
    conteudo = caminho.read_bytes()
    shutil.rmtree(pasta, ignore_errors=True)
    return SimpleUploadedFile(nome, conteudo, content_type="application/pdf")


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT, CELERY_TASK_ALWAYS_EAGER=True)
class PaginaEstourosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        modelo = get_user_model()
        cls.dono = modelo.objects.create_user(username="dono", password=SENHA_TESTE)
        cls.outro = modelo.objects.create_user(username="outro", password=SENHA_TESTE)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.client.force_login(self.dono)

    def _enviar(self, arquivos, **campos):
        dados = {
            "unidade": "cm",
            "modo_tamanho": "igual",
            "todos": "1",
            "preenchimento": "espelhar",
            "cor": "#FFFFFF",
            "referencia": "pagina",
            **campos,
            "arquivos": arquivos,
        }
        return self.client.post(reverse("estouros:inicio"), dados)

    def test_pagina_abre_e_aparece_no_menu(self):
        resposta = self.client.get(reverse("estouros:inicio"))
        self.assertContains(resposta, "Estouro para testeiras")
        self.assertContains(resposta, 'href="/estouros/"')

    def test_exige_login(self):
        self.client.logout()
        resposta = self.client.get(reverse("estouros:inicio"))
        self.assertEqual(resposta.status_code, 302)
        self.assertIn("/login/", resposta["Location"])

    def test_envio_processa_e_entrega_pdf_com_estouro(self):
        resposta = self._enviar([_upload("Testeira FETRAF.pdf")], todos="2,5")
        lote = LoteEstouro.objects.get()
        self.assertRedirects(resposta, reverse("estouros:lote", args=[lote.pk]))
        lote.refresh_from_db()
        self.assertEqual(lote.status, LoteEstouro.Status.CONCLUIDO)
        arquivo = lote.arquivos.get()
        self.assertEqual(arquivo.nome_resultado, "Testeira FETRAF_estouro-2,5cm.pdf")
        self.assertTrue(arquivo.previa)
        self.assertEqual(arquivo.medidas_cm["depois"], "19,1 × 12,1 cm")

        baixado = self.client.get(reverse("estouros:baixar", args=[arquivo.pk]))
        self.assertEqual(baixado["Content-Type"], "application/pdf")
        self.assertIn("estouro-2,5cm.pdf", baixado["Content-Disposition"])
        corpo = b"".join(baixado.streaming_content)
        with pikepdf.open(io.BytesIO(corpo)) as pdf:
            trim = [float(v) for v in pdf.pages[0].obj.TrimBox]
            self.assertEqual(trim, [0, 0, 400, 200])

    def test_tamanho_por_lado_e_por_eixo(self):
        self._enviar(
            [_upload()], modo_tamanho="lados", topo="1", direita="0", base="2", esquerda="0,5"
        )
        lote = LoteEstouro.objects.latest("pk")
        self.assertEqual(
            [lote.configuracao[k] for k in ("topo", "direita", "base", "esquerda")],
            ["1", "0", "2", "0.5"],
        )
        self._enviar([_upload()], modo_tamanho="eixos", horizontal="3", vertical="1")
        lote = LoteEstouro.objects.latest("pk")
        self.assertEqual(
            [lote.configuracao[k] for k in ("topo", "direita", "base", "esquerda")],
            ["1", "3", "1", "3"],
        )

    def test_varios_arquivos_viram_zip_com_os_mesmos_bytes(self):
        self._enviar(
            [_upload("a.pdf"), _upload("b.pdf"), _upload("a.pdf")], unidade="mm", todos="5"
        )
        lote = LoteEstouro.objects.get()
        resposta = self.client.get(reverse("estouros:baixar-zip", args=[lote.pk]))
        corpo = b"".join(resposta.streaming_content)
        with zipfile.ZipFile(io.BytesIO(corpo)) as zf:
            nomes = zf.namelist()
            self.assertEqual(
                nomes, ["a_estouro-5mm.pdf", "b_estouro-5mm.pdf", "a_estouro-5mm (2).pdf"]
            )
            primeiro = lote.arquivos.order_by("ordem").first()
            assert primeiro is not None
            self.assertEqual(zf.read(nomes[0]), Path(primeiro.resultado.path).read_bytes())

    def test_um_arquivo_ruim_nao_derruba_os_outros(self):
        ruim = SimpleUploadedFile("ruim.pdf", b"%PDF-1.4 quebrado", content_type="application/pdf")
        self._enviar([_upload("bom.pdf"), ruim])
        lote = LoteEstouro.objects.get()
        self.assertEqual(lote.status, LoteEstouro.Status.CONCLUIDO_COM_FALHAS)
        ruim_db = lote.arquivos.get(nome_original="ruim.pdf")
        self.assertEqual(ruim_db.status, ArquivoEstouro.Status.FALHOU)
        self.assertIn("não é um PDF válido", ruim_db.erro)
        pagina = self.client.get(reverse("estouros:lote", args=[lote.pk]))
        self.assertContains(pagina, "não é um PDF válido")

    def test_validacoes_do_formulario(self):
        nao_pdf = SimpleUploadedFile("foto.png", b"\x89PNG....", content_type="image/png")
        resposta = self._enviar([nao_pdf])
        self.assertContains(resposta, "não é um PDF", status_code=400)
        resposta = self._enviar([_upload()], todos="0")
        self.assertContains(resposta, "pelo menos um lado", status_code=400)
        resposta = self._enviar([_upload()], todos="150")
        self.assertContains(resposta, "máximo de 100 cm", status_code=400)
        self.assertFalse(LoteEstouro.objects.exists())

    @override_settings(ESTOUROS_MAX_ARQUIVOS=2)
    def test_limite_de_arquivos(self):
        resposta = self._enviar([_upload(), _upload(), _upload()])
        self.assertContains(resposta, "no máximo 2 arquivos", status_code=400)

    def test_outro_usuario_nao_ve_nem_baixa(self):
        self._enviar([_upload()])
        lote = LoteEstouro.objects.get()
        arquivo = lote.arquivos.get()
        self.client.force_login(self.outro)
        for url in (
            reverse("estouros:lote", args=[lote.pk]),
            reverse("estouros:baixar", args=[arquivo.pk]),
            reverse("estouros:previa", args=[arquivo.pk]),
            reverse("estouros:baixar-zip", args=[lote.pk]),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("estouros:status", args=[lote.pk])).status_code, 404
        )
        self.assertEqual(
            self.client.post(reverse("estouros:excluir", args=[lote.pk])).status_code, 404
        )
        self.assertNotContains(
            self.client.get(reverse("estouros:inicio")), lote.resumo_configuracao
        )

    def test_excluir_apaga_os_arquivos_do_disco(self):
        self._enviar([_upload(), _upload("b.pdf")])
        lote = LoteEstouro.objects.get()
        caminhos = [Path(a.resultado.path) for a in lote.arquivos.all()]
        caminhos += [Path(a.original.path) for a in lote.arquivos.all()]
        caminhos.append(Path(lote.zip_file.path))
        self.assertTrue(all(c.exists() for c in caminhos))
        self.client.post(reverse("estouros:excluir", args=[lote.pk]))
        self.assertFalse(any(c.exists() for c in caminhos))

    def test_status_em_json(self):
        self._enviar([_upload()])
        lote = LoteEstouro.objects.get()
        dados = self.client.get(reverse("estouros:status", args=[lote.pk])).json()
        self.assertFalse(dados["em_andamento"])
        self.assertEqual(dados["arquivos"][0]["status"], "concluido")

    def test_processar_duas_vezes_nao_reprocessa(self):
        self._enviar([_upload()])
        lote = LoteEstouro.objects.get()
        modificado = lote.arquivos.get().updated_at
        processar_lote(lote.pk)
        self.assertEqual(lote.arquivos.get().updated_at, modificado)

    def test_reabrir_um_envio_preenche_a_configuracao(self):
        self._enviar([_upload()], modo_tamanho="eixos", horizontal="3", vertical="1")
        lote = LoteEstouro.objects.get()
        pagina = self.client.get(reverse("estouros:lote", args=[lote.pk]))
        form = pagina.context["form"]
        self.assertEqual(form.initial["modo_tamanho"], "eixos")
        self.assertEqual(form.initial["horizontal"], "3")


class RetencaoTests(TestCase):
    def test_estouros_expiram_para_todos_os_usuarios(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.cleanup import cleanup_expired_records

        usuario = get_user_model().objects.create_user(username="real", password=SENHA_TESTE)
        velho = LoteEstouro.objects.create(user=usuario, configuracao={})
        novo = LoteEstouro.objects.create(user=usuario, configuracao={})
        LoteEstouro.objects.filter(pk=velho.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )
        resultado = cleanup_expired_records()
        self.assertEqual(resultado["deleted_estouros"], 1)
        self.assertEqual(list(LoteEstouro.objects.values_list("pk", flat=True)), [novo.pk])


class FormularioTests(SimpleTestCase):
    def test_sufixo_do_nome(self):
        from decimal import Decimal

        self.assertEqual(sufixo_arquivo([Decimal("3")] * 4, "cm"), "estouro-3cm")
        self.assertEqual(
            sufixo_arquivo([Decimal("1"), Decimal("2.5"), Decimal("1"), Decimal("0")], "cm"),
            "estouro-1-2,5-1-0cm",
        )

    def test_aceita_virgula_decimal(self):
        form = EstouroForm(
            data={
                "unidade": "cm",
                "modo_tamanho": "igual",
                "todos": "1,5",
                "preenchimento": "cor",
                "cor": "#112233",
                "referencia": "pagina",
            },
            files={"arquivos": _upload()},
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.configuracao_json()["topo"], "1.5")
