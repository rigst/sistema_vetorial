"""Formulário da página de estouros: arquivos + configuração."""

from __future__ import annotations

from decimal import Decimal

from django import forms
from django.conf import settings

from .pdf import PREENCHIMENTOS, Configuracao, Lados

UNIDADES = [("cm", "Centímetros (cm)"), ("mm", "Milímetros (mm)"), ("pol", "Polegadas (pol)")]

MODOS_TAMANHO = [
    ("igual", "Igual nos 4 lados"),
    ("eixos", "Horizontal e vertical"),
    ("lados", "Um valor por lado"),
]

ROTULOS_PREENCHIMENTO = {
    "espelhar": "Espelhar a arte",
    "esticar": "Esticar a borda",
    "cor": "Cor sólida",
    "branco": "Sem preenchimento (fundo branco)",
}

REFERENCIAS = [
    ("pagina", "A partir da borda da página"),
    ("corte", "A partir da linha de corte (TrimBox), quando o PDF tiver"),
]

# Teto de sanidade por lado (1 m): evita página gigante por engano de unidade.
MAXIMO_CM = Decimal("100")
CM_POR_UNIDADE = {"cm": Decimal("1"), "mm": Decimal("0.1"), "pol": Decimal("2.54")}


class VariosArquivosInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class VariosArquivosField(forms.FileField):
    widget = VariosArquivosInput

    def clean(self, data, initial=None):
        unico = super().clean
        if isinstance(data, list | tuple):
            return [unico(arquivo, initial) for arquivo in data]
        return [unico(data, initial)] if data else []


def _medida(rotulo: str, inicial=None) -> forms.DecimalField:
    return forms.DecimalField(
        label=rotulo,
        required=False,
        min_value=Decimal("0"),
        max_digits=7,
        decimal_places=3,
        initial=inicial,
        localize=True,
        widget=forms.TextInput(attrs={"inputmode": "decimal", "autocomplete": "off"}),
    )


def _cor_rgb(hexa: str) -> tuple[float, float, float]:
    hexa = hexa.lstrip("#")
    return (int(hexa[0:2], 16) / 255, int(hexa[2:4], 16) / 255, int(hexa[4:6], 16) / 255)


class EstouroForm(forms.Form):
    arquivos = VariosArquivosField(
        label="PDFs",
        widget=VariosArquivosInput(attrs={"accept": ".pdf,application/pdf"}),
    )
    unidade = forms.ChoiceField(label="Unidade", choices=UNIDADES, initial="cm")
    modo_tamanho = forms.ChoiceField(
        label="Tamanho do estouro", choices=MODOS_TAMANHO, initial="igual", widget=forms.RadioSelect
    )
    todos = _medida("Todos os lados", Decimal("3"))
    horizontal = _medida("Esquerda e direita")
    vertical = _medida("Topo e base")
    topo = _medida("Topo")
    direita = _medida("Direita")
    base = _medida("Base")
    esquerda = _medida("Esquerda")
    preenchimento = forms.ChoiceField(
        label="Como preencher o estouro",
        choices=[(p, ROTULOS_PREENCHIMENTO[p]) for p in PREENCHIMENTOS],
        initial="espelhar",
        widget=forms.RadioSelect,
    )
    cor = forms.RegexField(
        label="Cor do estouro",
        regex=r"^#[0-9A-Fa-f]{6}$",
        initial="#FFFFFF",
        required=False,
        widget=forms.TextInput(attrs={"type": "color"}),
    )
    referencia = forms.ChoiceField(
        label="Medir o estouro", choices=REFERENCIAS, initial="pagina", widget=forms.RadioSelect
    )
    marcas_corte = forms.BooleanField(
        label="Adicionar marcas de corte",
        required=False,
        help_text="Linhas finas fora do estouro, alinhadas à linha de corte.",
    )

    def clean_arquivos(self):
        arquivos = self.cleaned_data["arquivos"]
        if not arquivos:
            raise forms.ValidationError("Envie pelo menos um PDF.")
        limite = settings.ESTOUROS_MAX_ARQUIVOS
        if len(arquivos) > limite:
            raise forms.ValidationError(f"Envie no máximo {limite} arquivos por vez.")
        for arquivo in arquivos:
            if not arquivo.name.lower().endswith(".pdf"):
                raise forms.ValidationError(f"“{arquivo.name}” não é um PDF.")
            arquivo.seek(0)
            cabecalho = arquivo.read(1024)
            arquivo.seek(0)
            if b"%PDF-" not in cabecalho:
                raise forms.ValidationError(f"“{arquivo.name}” não é um PDF válido.")
        return arquivos

    def _lados(self, dados) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        def v(nome):
            return dados.get(nome) or Decimal("0")

        modo = dados.get("modo_tamanho")
        if modo == "igual":
            return v("todos"), v("todos"), v("todos"), v("todos")
        if modo == "eixos":
            return v("vertical"), v("horizontal"), v("vertical"), v("horizontal")
        return v("topo"), v("direita"), v("base"), v("esquerda")

    def clean(self):
        dados = super().clean() or {}
        unidade = dados.get("unidade") or "cm"
        lados = self._lados(dados)
        if not any(lados) and not dados.get("marcas_corte"):
            raise forms.ValidationError("Informe o tamanho do estouro em pelo menos um lado.")
        if any(valor * CM_POR_UNIDADE[unidade] > MAXIMO_CM for valor in lados):
            raise forms.ValidationError("O estouro está muito grande (máximo de 100 cm por lado).")
        if dados.get("preenchimento") == "cor" and not dados.get("cor"):
            self.add_error("cor", "Escolha a cor do estouro.")
        dados["lados"] = lados
        return dados

    # ----------------------------------------------------- saída para o lote

    def configuracao_json(self) -> dict:
        d = self.cleaned_data
        topo, direita, base, esquerda = (str(v) for v in d["lados"])
        return {
            "unidade": d["unidade"],
            "topo": topo,
            "direita": direita,
            "base": base,
            "esquerda": esquerda,
            "preenchimento": d["preenchimento"],
            "cor": (d.get("cor") or "#FFFFFF").upper(),
            "referencia": d["referencia"],
            "marcas_corte": bool(d.get("marcas_corte")),
            "sufixo": sufixo_arquivo(d["lados"], d["unidade"]),
        }


def configuracao_do_lote(dados: dict) -> Configuracao:
    lados = Lados.na_unidade(
        dados["unidade"], dados["topo"], dados["direita"], dados["base"], dados["esquerda"]
    )
    return Configuracao(
        lados=lados,
        preenchimento=dados["preenchimento"],
        cor=_cor_rgb(dados.get("cor") or "#FFFFFF"),
        referencia=dados.get("referencia", "pagina"),
        marcas_corte=bool(dados.get("marcas_corte")),
    )


def _fmt(valor) -> str:
    texto = f"{Decimal(str(valor)):f}".rstrip("0").rstrip(".")
    return (texto or "0").replace(".", ",")


def sufixo_arquivo(lados, unidade: str) -> str:
    valores = {_fmt(v) for v in lados}
    if len(valores) == 1:
        return f"estouro-{valores.pop()}{unidade}"
    return "estouro-" + "-".join(_fmt(v) for v in lados) + unidade


def resumo_configuracao(dados: dict) -> str:
    unidade = dados["unidade"]
    lados = [dados[k] for k in ("topo", "direita", "base", "esquerda")]
    valores = [_fmt(v) for v in lados]
    if len(set(valores)) == 1:
        tamanho = f"{valores[0]} {unidade} em todos os lados"
    else:
        nomes = ("topo", "direita", "base", "esquerda")
        tamanho = (
            " · ".join(f"{n} {v}" for n, v in zip(nomes, valores, strict=True)) + f" {unidade}"
        )
    extra = ROTULOS_PREENCHIMENTO[dados["preenchimento"]].split(" (")[0].lower()
    if dados["preenchimento"] == "cor":
        extra += f" {dados.get('cor', '')}"
    if dados.get("marcas_corte"):
        extra += " · marcas de corte"
    return f"{tamanho} · {extra}"
