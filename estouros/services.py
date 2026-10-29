"""Processamento de um lote de estouro: aplica, gera prévias e o ZIP."""

from __future__ import annotations

import logging
import subprocess
import tempfile
import zipfile
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile
from django.db import transaction

from .forms import configuracao_do_lote
from .models import ArquivoEstouro, LoteEstouro
from .pdf import ErroEstouro, aplicar_estouro

logger = logging.getLogger(__name__)

# Lado maior da prévia em pixels (só para a tela; o PDF não é tocado).
PREVIA_PX = 900


def _gerar_previa(pdf_path: Path, destino_prefixo: Path) -> Path | None:
    try:
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-singlefile",
                "-f",
                "1",
                "-l",
                "1",
                "-cropbox",
                "-scale-to",
                str(PREVIA_PX),
                str(pdf_path),
                str(destino_prefixo),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        logger.warning("Prévia do estouro não gerada", exc_info=True)
        return None
    gerado = destino_prefixo.with_suffix(".png")
    return gerado if gerado.exists() else None


def _medidas(resultado) -> dict:
    p = resultado.primeira
    return {
        "largura_antes": p.largura_antes,
        "altura_antes": p.altura_antes,
        "largura_depois": p.largura_depois,
        "altura_depois": p.altura_depois,
        "corte": list(p.corte_fracao),
    }


def processar_arquivo(arquivo: ArquivoEstouro, config) -> None:
    with tempfile.TemporaryDirectory(prefix="estouro-") as tmp:
        pasta = Path(tmp)
        saida = pasta / "saida.pdf"
        try:
            resultado = aplicar_estouro(arquivo.original.path, saida, config)
        except ErroEstouro as exc:
            arquivo.status = ArquivoEstouro.Status.FALHOU
            arquivo.erro = str(exc)
            arquivo.save(update_fields=["status", "erro", "updated_at"])
            return
        except Exception:
            logger.exception("Falha inesperada no estouro", extra={"arquivo_id": arquivo.pk})
            arquivo.status = ArquivoEstouro.Status.FALHOU
            arquivo.erro = (
                "Não foi possível processar este PDF. Verifique se ele abre normalmente "
                "e envie de novo."
            )
            arquivo.save(update_fields=["status", "erro", "updated_at"])
            return

        with saida.open("rb") as gerado:
            arquivo.resultado.save(arquivo.nome_resultado, File(gerado), save=False)
        previa = _gerar_previa(saida, pasta / "previa")
        if previa:
            with previa.open("rb") as imagem:
                arquivo.previa.save(f"previa-{arquivo.pk}.png", File(imagem), save=False)
        arquivo.paginas = resultado.paginas
        arquivo.medidas = _medidas(resultado)
        arquivo.status = ArquivoEstouro.Status.CONCLUIDO
        arquivo.erro = ""
        arquivo.save()


def _nome_unico(nome: str, usados: set[str]) -> str:
    candidato, n = nome, 2
    while candidato.lower() in usados:
        base = nome[:-4] if nome.lower().endswith(".pdf") else nome
        candidato = f"{base} ({n}).pdf"
        n += 1
    usados.add(candidato.lower())
    return candidato


def _montar_zip(lote: LoteEstouro) -> None:
    prontos = [a for a in lote.arquivos.all() if a.status == ArquivoEstouro.Status.CONCLUIDO]
    if len(prontos) < 2:
        return
    conteudo = tempfile.SpooledTemporaryFile(max_size=50 * 1024 * 1024)
    usados: set[str] = set()
    # ZIP_STORED: PDF já vem comprimido, e assim os bytes dentro do ZIP são
    # exatamente os do PDF baixado avulso.
    with zipfile.ZipFile(conteudo, "w", compression=zipfile.ZIP_STORED) as zf:
        for arquivo in prontos:
            zf.write(arquivo.resultado.path, _nome_unico(arquivo.nome_resultado, usados))
    conteudo.seek(0)
    lote.zip_file.save(f"estouros-{lote.pk}.zip", ContentFile(conteudo.read()), save=False)


def processar_lote(lote_id: int) -> None:
    with transaction.atomic():
        lote = LoteEstouro.objects.select_for_update().filter(pk=lote_id).first()
        if lote is None or lote.status != LoteEstouro.Status.NA_FILA:
            return
        lote.status = LoteEstouro.Status.PROCESSANDO
        lote.save(update_fields=["status", "updated_at"])

    try:
        config = configuracao_do_lote(lote.configuracao)
        for arquivo in lote.arquivos.filter(status=ArquivoEstouro.Status.PENDENTE):
            processar_arquivo(arquivo, config)
        _montar_zip(lote)
    except Exception:
        logger.exception("Falha no lote de estouro", extra={"lote_id": lote.pk})
        lote.status = LoteEstouro.Status.FALHOU
        lote.erro = "O processamento falhou. Tente enviar os arquivos de novo."
        lote.save(update_fields=["status", "erro", "updated_at"])
        return

    falhas = lote.arquivos.filter(status=ArquivoEstouro.Status.FALHOU).count()
    total = lote.arquivos.count()
    if falhas == total:
        lote.status = LoteEstouro.Status.FALHOU
        lote.erro = "Nenhum arquivo pôde ser processado."
    elif falhas:
        lote.status = LoteEstouro.Status.CONCLUIDO_COM_FALHAS
    else:
        lote.status = LoteEstouro.Status.CONCLUIDO
    lote.save()


def criar_lote(user, form) -> LoteEstouro:
    from .forms import resumo_configuracao

    configuracao = form.configuracao_json()
    with transaction.atomic():
        lote = LoteEstouro.objects.create(
            user=user,
            configuracao=configuracao,
            resumo_configuracao=resumo_configuracao(configuracao)[:255],
        )
        for ordem, enviado in enumerate(form.cleaned_data["arquivos"]):
            nome = Path(enviado.name).name[:200]
            arquivo = ArquivoEstouro(lote=lote, ordem=ordem, nome_original=nome)
            arquivo.original.save(nome, enviado, save=False)
            arquivo.save()
    return lote
