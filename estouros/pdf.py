"""Estouro (sangria) em PDFs, sem reamostrar nem recomprimir nada.

Como funciona, página a página:

1. A página **cresce para fora**: o conteúdo original continua exatamente nas
   mesmas coordenadas, com os mesmos content streams e as mesmas imagens
   (byte a byte). Não há escala, não há rasterização.
2. O conteúdo original é recortado na caixa que ele já ocupava, para que nada
   escondido fora dela (arte além da CropBox, por exemplo) apareça no estouro.
3. A faixa nova é preenchida por baixo, conforme o modo escolhido:
   - ``espelhar``: a própria página, desenhada de novo como Form XObject,
     refletida na borda (vetorial: as imagens são as mesmas, só referenciadas);
   - ``esticar``: uma faixa fina da borda (``FAIXA_ESTICAR_PT``) ampliada até
     cobrir o estouro — o efeito de "puxar a borda";
   - ``cor``: retângulos de cor sólida só na faixa nova;
   - ``branco``: a página só cresce.
4. As caixas ficam no padrão de gráfica: ``TrimBox`` = linha de corte (a arte
   original), ``BleedBox`` = arte + estouro, ``MediaBox``/``CropBox`` = folha
   inteira (com as marcas de corte, quando pedidas).

As medidas pedidas são *visuais* (como a pessoa vê a página): com ``/Rotate``,
o "topo" é convertido para o lado certo do espaço da página. ``/UserUnit`` é
respeitado na conversão de centímetros para unidades da página.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pikepdf

PT_POR_UNIDADE = {
    "mm": 72 / 25.4,
    "cm": 72 / 2.54,
    "pol": 72.0,
    "pt": 1.0,
}

# Largura da faixa da borda usada no modo "esticar" (em pontos visuais).
FAIXA_ESTICAR_PT = 1.0

# Marcas de corte: afastamento a partir do estouro, comprimento e espessura.
MARCA_AFASTAMENTO_PT = 3 * 72 / 25.4
MARCA_COMPRIMENTO_PT = 5 * 72 / 25.4
MARCA_MARGEM_PT = MARCA_AFASTAMENTO_PT + MARCA_COMPRIMENTO_PT + 2 * 72 / 25.4
MARCA_ESPESSURA_PT = 0.25

PREENCHIMENTOS = ("espelhar", "esticar", "cor", "branco")
REFERENCIAS = ("pagina", "corte")


class ErroEstouro(ValueError):
    """Erro de entrada que a pessoa consegue corrigir (mensagem em português)."""


@dataclass(frozen=True)
class Lados:
    """Estouro por lado, em pontos, na orientação em que a página é vista."""

    topo: float = 0.0
    direita: float = 0.0
    base: float = 0.0
    esquerda: float = 0.0

    @classmethod
    def na_unidade(cls, unidade: str, topo, direita, base, esquerda) -> Lados:
        fator = PT_POR_UNIDADE[unidade]
        return cls(*(float(v) * fator for v in (topo, direita, base, esquerda)))

    def maior(self) -> float:
        return max(self.topo, self.direita, self.base, self.esquerda)


@dataclass(frozen=True)
class Configuracao:
    lados: Lados
    preenchimento: str = "espelhar"
    cor: tuple[float, float, float] = (1.0, 1.0, 1.0)
    referencia: str = "pagina"
    marcas_corte: bool = False

    def __post_init__(self):
        if self.preenchimento not in PREENCHIMENTOS:
            raise ErroEstouro(f"Preenchimento desconhecido: {self.preenchimento}.")
        if self.referencia not in REFERENCIAS:
            raise ErroEstouro(f"Referência desconhecida: {self.referencia}.")


@dataclass(frozen=True)
class Caixa:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def largura(self) -> float:
        return self.x1 - self.x0

    @property
    def altura(self) -> float:
        return self.y1 - self.y0

    def intersecao(self, outra: Caixa) -> Caixa:
        return Caixa(
            max(self.x0, outra.x0),
            max(self.y0, outra.y0),
            min(self.x1, outra.x1),
            min(self.y1, outra.y1),
        )

    def expandida(self, esquerda: float, base: float, direita: float, topo: float) -> Caixa:
        return Caixa(self.x0 - esquerda, self.y0 - base, self.x1 + direita, self.y1 + topo)

    def como_array(self) -> pikepdf.Array:
        return pikepdf.Array([_num(v) for v in (self.x0, self.y0, self.x1, self.y1)])

    def valida(self) -> bool:
        return self.largura > 0 and self.altura > 0


@dataclass(frozen=True)
class ResumoPagina:
    """Medidas visuais (como a página é vista), em pontos reais."""

    largura_antes: float
    altura_antes: float
    largura_depois: float
    altura_depois: float
    # Linha de corte dentro da folha final, em frações (0–1) a partir do canto
    # superior esquerdo visual — para desenhar a prévia.
    corte_fracao: tuple[float, float, float, float]


@dataclass(frozen=True)
class Resultado:
    paginas: int
    primeira: ResumoPagina


# --------------------------------------------------------------- utilidades


def _num(valor: float) -> float:
    """Arredonda a 4 casas: evita ruído de ponto flutuante nas caixas."""
    return round(float(valor), 4)


def _fmt(valor: float) -> str:
    texto = f"{valor:.4f}".rstrip("0").rstrip(".")
    return texto if texto not in ("", "-0") else "0"


def _herdado(pagina: pikepdf.Page, chave: str):
    """Atributo herdável da árvore de páginas (/Resources, /Rotate, caixas)."""
    no: pikepdf.Object | None = pagina.obj
    while isinstance(no, pikepdf.Dictionary):
        if chave in no:
            return no[chave]
        no = no.get("/Parent")
    return None


def _caixa(valor) -> Caixa | None:
    if valor is None:
        return None
    a, b, c, d = (float(v) for v in valor)
    return Caixa(min(a, c), min(b, d), max(a, c), max(b, d))


def _user_unit(pagina: pikepdf.Page) -> float:
    """/UserUnit (PDF 1.6): tamanho da unidade da página em pontos. O pikepdf
    devolve número do PDF como int ou Decimal."""
    valor = pagina.obj.get("/UserUnit")
    if isinstance(valor, int | float | Decimal) and valor > 0:
        return float(valor)
    return 1.0


def _rotacao(pagina: pikepdf.Page) -> int:
    valor = _herdado(pagina, "/Rotate")
    rotacao = int(valor or 0) % 360
    return rotacao if rotacao % 90 == 0 else 0


def lados_no_espaco_da_pagina(lados: Lados, rotacao: int) -> tuple[float, float, float, float]:
    """Converte (topo, direita, base, esquerda) visuais para (esquerda, base,
    direita, topo) do espaço da página, considerando o /Rotate.

    O /Rotate gira a página no sentido horário para exibição. Com 90°, o lado
    esquerdo do espaço da página aparece em cima; o topo aparece à direita.
    """
    t, r, b, e = lados.topo, lados.direita, lados.base, lados.esquerda
    if rotacao == 90:
        # visual: topo=esq, direita=topo, base=dir, esquerda=base
        return t, e, b, r
    if rotacao == 180:
        return r, t, e, b
    if rotacao == 270:
        return b, r, t, e
    return e, b, r, t


# ------------------------------------------------------------- desenho


def _ret(caixa: Caixa) -> str:
    return f"{_fmt(caixa.x0)} {_fmt(caixa.y0)} {_fmt(caixa.largura)} {_fmt(caixa.altura)} re"


def _cm(a: float, b: float, c: float, d: float, e: float, f: float) -> str:
    return " ".join(_fmt(v) for v in (a, b, c, d, e, f)) + " cm"


def _faixas(conteudo: Caixa, folha: Caixa) -> dict[str, Caixa]:
    """As 8 regiões de estouro (4 laterais + 4 cantos) que têm área."""
    c, f = conteudo, folha
    regioes = {
        "esquerda": Caixa(f.x0, c.y0, c.x0, c.y1),
        "direita": Caixa(c.x1, c.y0, f.x1, c.y1),
        "base": Caixa(c.x0, f.y0, c.x1, c.y0),
        "topo": Caixa(c.x0, c.y1, c.x1, f.y1),
        "base_esquerda": Caixa(f.x0, f.y0, c.x0, c.y0),
        "base_direita": Caixa(c.x1, f.y0, f.x1, c.y0),
        "topo_esquerda": Caixa(f.x0, c.y1, c.x0, f.y1),
        "topo_direita": Caixa(c.x1, c.y1, f.x1, f.y1),
    }
    return {nome: r for nome, r in regioes.items() if r.largura > 1e-6 and r.altura > 1e-6}


def _eixo_espelho(nome: str, c: Caixa) -> tuple[float, float, float, float]:
    """(sx, ex, sy, ey) da reflexão na borda: x' = sx*x + ex, y' = sy*y + ey."""
    sx, ex, sy, ey = 1.0, 0.0, 1.0, 0.0
    if "esquerda" in nome:
        sx, ex = -1.0, 2 * c.x0
    if "direita" in nome:
        sx, ex = -1.0, 2 * c.x1
    if nome.startswith("base"):
        sy, ey = -1.0, 2 * c.y0
    if nome.startswith("topo"):
        sy, ey = -1.0, 2 * c.y1
    return sx, ex, sy, ey


def _eixo_esticar(nome: str, c: Caixa, r: Caixa, faixa: float):
    """Reflexão ampliada de uma faixa de largura ``faixa`` junto à borda: o
    lado colado na arte continua contínuo e o resto vira a borda puxada."""
    sx, ex, sy, ey = 1.0, 0.0, 1.0, 0.0
    if "esquerda" in nome:
        k = r.largura / min(faixa, c.largura)
        sx, ex = -k, c.x0 * (1 + k)
    if "direita" in nome:
        k = r.largura / min(faixa, c.largura)
        sx, ex = -k, c.x1 * (1 + k)
    if nome.startswith("base"):
        k = r.altura / min(faixa, c.altura)
        sy, ey = -k, c.y0 * (1 + k)
    if nome.startswith("topo"):
        k = r.altura / min(faixa, c.altura)
        sy, ey = -k, c.y1 * (1 + k)
    return sx, ex, sy, ey


def _desenho_estouro(
    config: Configuracao, conteudo: Caixa, folha: Caixa, nome_form: str, unidade_usuario: float
) -> str:
    regioes = _faixas(conteudo, folha)
    if not regioes or config.preenchimento == "branco":
        return ""
    partes = ["q"]
    if config.preenchimento == "cor":
        r, g, b = config.cor
        partes.append(f"{_fmt(r)} {_fmt(g)} {_fmt(b)} rg")
        partes += [f"{_ret(reg)} f" for reg in regioes.values()]
    else:
        faixa = FAIXA_ESTICAR_PT / unidade_usuario
        for nome, reg in regioes.items():
            if config.preenchimento == "espelhar":
                sx, ex, sy, ey = _eixo_espelho(nome, conteudo)
            else:
                sx, ex, sy, ey = _eixo_esticar(nome, conteudo, reg, faixa)
            partes.append(f"q {_ret(reg)} W n {_cm(sx, 0, 0, sy, ex, ey)} /{nome_form} Do Q")
    partes.append("Q")
    return "\n".join(partes)


def _marcas_de_corte(corte: Caixa, estouro: Caixa, unidade_usuario: float) -> str:
    afast = MARCA_AFASTAMENTO_PT / unidade_usuario
    comp = MARCA_COMPRIMENTO_PT / unidade_usuario
    linhas = []
    for x in (corte.x0, corte.x1):
        linhas.append((x, estouro.y0 - afast, x, estouro.y0 - afast - comp))
        linhas.append((x, estouro.y1 + afast, x, estouro.y1 + afast + comp))
    for y in (corte.y0, corte.y1):
        linhas.append((estouro.x0 - afast, y, estouro.x0 - afast - comp, y))
        linhas.append((estouro.x1 + afast, y, estouro.x1 + afast + comp, y))
    partes = ["q", f"{_fmt(MARCA_ESPESSURA_PT / unidade_usuario)} w", "0 0 0 1 K", "0 J"]
    partes += [f"{_fmt(a)} {_fmt(b)} m {_fmt(c)} {_fmt(d)} l S" for a, b, c, d in linhas]
    partes.append("Q")
    return "\n".join(partes)


# --------------------------------------------------------- por página


def _recursos_com_form(pdf: pikepdf.Pdf, recursos, nome: str, form) -> pikepdf.Dictionary:
    """Recursos novos para a página: as mesmas entradas (por referência, nada é
    copiado de verdade) mais o Form XObject do estouro. Não se altera o
    dicionário original, que pode ser compartilhado com outras páginas e é o
    mesmo que o próprio form usa."""
    novo = pikepdf.Dictionary()
    if recursos is not None:
        for chave, valor in recursos.items():
            novo[chave] = valor
    xobjs = pikepdf.Dictionary()
    antigos = recursos.get("/XObject") if recursos is not None else None
    if antigos is not None:
        for chave, valor in antigos.items():
            xobjs[chave] = valor
    xobjs[f"/{nome}"] = form
    novo["/XObject"] = xobjs
    return novo


def _form_da_pagina(pdf: pikepdf.Pdf, pagina: pikepdf.Page, media: Caixa, recursos):
    """O desenho da página como Form XObject, usado só nas faixas de estouro.

    Com um único content stream (o caso comum, e o de arquivos do Illustrator),
    o form é uma cópia dos bytes **comprimidos** do stream original, com o
    mesmo filtro: nada é descomprimido nem recomprimido. Com vários streams,
    eles são concatenados (sem perdas). As imagens são referenciadas, não
    copiadas: o arquivo cresce só o tamanho comprimido do desenho.
    """
    atuais = pagina.obj.get("/Contents")
    form: pikepdf.Object
    if isinstance(atuais, pikepdf.Stream):
        form = pikepdf.Stream(pdf, atuais.read_raw_bytes())
        for chave in ("/Filter", "/DecodeParms"):
            if chave in atuais.stream_dict:
                form.stream_dict[chave] = atuais.stream_dict[chave]
        form.stream_dict["/Type"] = pikepdf.Name.XObject
        form.stream_dict["/Subtype"] = pikepdf.Name.Form
        if "/Group" in pagina.obj:
            form.stream_dict["/Group"] = pagina.obj["/Group"]
    else:
        form = pagina.as_form_xobject(False)
    form["/BBox"] = media.como_array()
    form["/Resources"] = recursos if recursos is not None else pikepdf.Dictionary()
    return pdf.make_indirect(form)


def _caixa_de_referencia(pagina: pikepdf.Page, config: Configuracao, visivel: Caixa) -> Caixa:
    if config.referencia == "corte":
        corte = _caixa(_herdado(pagina, "/TrimBox"))
        if corte is not None:
            corte = corte.intersecao(visivel)
            if corte.valida():
                return corte
    return visivel


def _resumo(
    visivel: Caixa, folha_final: Caixa, corte: Caixa, rotacao: int, uu: float
) -> ResumoPagina:
    def visual(caixa: Caixa) -> tuple[float, float]:
        if rotacao in (90, 270):
            return caixa.altura * uu, caixa.largura * uu
        return caixa.largura * uu, caixa.altura * uu

    w, h = folha_final.largura, folha_final.altura
    # frações no espaço da página, depois giradas para a vista
    fx0, fx1 = (corte.x0 - folha_final.x0) / w, (corte.x1 - folha_final.x0) / w
    fy0, fy1 = (folha_final.y1 - corte.y1) / h, (folha_final.y1 - corte.y0) / h
    esq, topo, dir_, base = fx0, fy0, fx1, fy1
    if rotacao == 90:
        esq, topo, dir_, base = 1 - fy1, fx0, 1 - fy0, fx1
    elif rotacao == 180:
        esq, topo, dir_, base = 1 - fx1, 1 - fy1, 1 - fx0, 1 - fy0
    elif rotacao == 270:
        esq, topo, dir_, base = fy0, 1 - fx1, fy1, 1 - fx0
    antes, depois = visual(visivel), visual(folha_final)
    return ResumoPagina(antes[0], antes[1], depois[0], depois[1], (esq, topo, dir_, base))


def _processar_pagina(
    pdf: pikepdf.Pdf, pagina: pikepdf.Page, indice: int, config: Configuracao
) -> ResumoPagina:
    uu = _user_unit(pagina)
    rotacao = _rotacao(pagina)
    media = _caixa(_herdado(pagina, "/MediaBox")) or Caixa(0, 0, 612, 792)
    recorte = _caixa(_herdado(pagina, "/CropBox")) or media
    visivel = recorte.intersecao(media)
    if not visivel.valida():
        visivel = media

    esq, base, dir_, topo = (v / uu for v in lados_no_espaco_da_pagina(config.lados, rotacao))
    referencia = _caixa_de_referencia(pagina, config, visivel)
    estouro = referencia.expandida(esq, base, dir_, topo)
    conteudo = visivel.intersecao(estouro)
    _validar_espelho(config, conteudo, estouro, uu, indice)

    recursos = _herdado(pagina, "/Resources")
    nome_form = f"EstouroP{indice + 1}"
    usa_form = config.preenchimento in ("espelhar", "esticar") and bool(_faixas(conteudo, estouro))
    if usa_form:
        form = _form_da_pagina(pdf, pagina, media, recursos)
        pagina.obj["/Resources"] = _recursos_com_form(pdf, recursos, nome_form, form)
    desenho = _desenho_estouro(config, conteudo, estouro, nome_form, uu)

    folha = estouro
    if config.marcas_corte:
        margem = MARCA_MARGEM_PT / uu
        folha = estouro.expandida(margem, margem, margem, margem)
        desenho = "\n".join(p for p in (desenho, _marcas_de_corte(referencia, estouro, uu)) if p)

    _montar_conteudo(pdf, pagina, desenho, conteudo)
    _gravar_caixas(pagina, folha, estouro, referencia, rotacao, uu)
    return _resumo(visivel, folha, referencia, rotacao, uu)


def _validar_espelho(config: Configuracao, conteudo: Caixa, estouro: Caixa, uu, indice) -> None:
    if config.preenchimento != "espelhar":
        return
    maior_x = max(conteudo.x0 - estouro.x0, estouro.x1 - conteudo.x1)
    maior_y = max(conteudo.y0 - estouro.y0, estouro.y1 - conteudo.y1)
    if maior_x > conteudo.largura + 1e-6 or maior_y > conteudo.altura + 1e-6:
        lado = min(conteudo.largura, conteudo.altura) * uu / PT_POR_UNIDADE["cm"]
        raise ErroEstouro(
            f"Página {indice + 1}: o estouro é maior que a própria arte ({lado:.1f} cm no "
            "lado menor), então não dá para espelhar. Use “esticar a borda” ou “cor sólida”."
        )


def _montar_conteudo(pdf: pikepdf.Pdf, pagina: pikepdf.Page, desenho: str, conteudo: Caixa):
    """Estouro por baixo; depois o conteúdo original, recortado na caixa que ele
    já ocupava. A arte é sempre desenhada pelos content streams originais,
    intactos: o form (espelhar/esticar) serve só às faixas de estouro. Desenhar
    a arte pelo form mudaria o caminho de renderização e já gera diferença de
    antisserrilhado nas bordas — a arte precisa sair pixel a pixel igual."""
    atuais = pagina.obj.get("/Contents")
    if atuais is None:
        originais = []
    elif isinstance(atuais, pikepdf.Array):
        originais = [atuais[i] for i in range(len(atuais))]
    else:
        originais = [atuais]
    novos: list[pikepdf.Object] = []
    if desenho:
        novos.append(pdf.make_stream(desenho.encode("ascii") + b"\n"))
    novos.append(pdf.make_stream(f"q {_ret(conteudo)} W n\n".encode("ascii")))
    novos += originais
    novos.append(pdf.make_stream(b"\nQ\n"))
    pagina.obj["/Contents"] = pikepdf.Array(novos)


def _gravar_caixas(pagina, folha: Caixa, estouro: Caixa, corte: Caixa, rotacao: int, uu: float):
    obj = pagina.obj
    obj["/MediaBox"] = folha.como_array()
    obj["/CropBox"] = folha.como_array()
    obj["/BleedBox"] = estouro.como_array()
    obj["/TrimBox"] = corte.como_array()
    arte = _caixa(obj.get("/ArtBox"))
    if arte is not None:
        arte = arte.intersecao(estouro)
        if arte.valida():
            obj["/ArtBox"] = arte.como_array()
        else:
            del obj["/ArtBox"]
    # Gravados na própria página: valores herdados da árvore continuariam
    # valendo, mas deixam de ser óbvios para quem inspeciona o arquivo.
    if rotacao:
        obj["/Rotate"] = rotacao
    if uu != 1:
        obj["/UserUnit"] = uu


# ------------------------------------------------------------- arquivo


def aplicar_estouro(
    origem: Path | str,
    destino: Path | str,
    config: Configuracao,
    progresso: Callable[[int, int], None] | None = None,
) -> Resultado:
    if config.lados.maior() <= 0 and not config.marcas_corte:
        raise ErroEstouro("Informe o tamanho do estouro em pelo menos um lado.")
    try:
        pdf = pikepdf.open(origem)
    except pikepdf.PasswordError as exc:
        raise ErroEstouro("O PDF está protegido por senha.") from exc
    except pikepdf.PdfError as exc:
        raise ErroEstouro("O arquivo não é um PDF válido ou está corrompido.") from exc
    with pdf:
        if pdf.is_encrypted:
            raise ErroEstouro(
                "O PDF tem restrições de segurança (criptografia). Salve uma cópia "
                "sem proteção e envie de novo."
            )
        total = len(pdf.pages)
        if not total:
            raise ErroEstouro("O PDF não tem páginas.")
        primeira = None
        for indice, pagina in enumerate(pdf.pages):
            resumo = _processar_pagina(pdf, pagina, indice, config)
            primeira = primeira or resumo
            if progresso:
                progresso(indice + 1, total)
        pdf.save(
            destino,
            # Nada é decodificado e recodificado: imagens e streams existentes
            # vão para o arquivo novo com os mesmos bytes.
            stream_decode_level=pikepdf.StreamDecodeLevel.none,
            recompress_flate=False,
            object_stream_mode=pikepdf.ObjectStreamMode.preserve,
            # Não comprime o que veio sem compressão (dados de edição do
            # Illustrator, miniatura): o arquivo sai com os mesmos bytes.
            compress_streams=False,
            # Mantém o XMP (metadados do Illustrator) exatamente como veio.
            fix_metadata_version=False,
        )
    assert primeira is not None
    return Resultado(paginas=total, primeira=primeira)


def em_unidade(pontos: float, unidade: str) -> float:
    valor = pontos / PT_POR_UNIDADE[unidade]
    return math.floor(valor * 100 + 0.5) / 100
