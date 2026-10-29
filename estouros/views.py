from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from .forms import EstouroForm
from .models import ArquivoEstouro, LoteEstouro
from .runner import disparar
from .services import criar_lote

LOTES_RECENTES = 10


def _lote_do_usuario(request, pk) -> LoteEstouro:
    return get_object_or_404(LoteEstouro, pk=pk, user=request.user)


class EstouroView(LoginRequiredMixin, View):
    """Página única: envio + configuração à esquerda, lotes recentes à direita."""

    template_name = "estouros/estouro.html"

    def _contexto(self, request, form, lote=None):
        return {
            "form": form,
            "lote": lote,
            "max_arquivos": settings.ESTOUROS_MAX_ARQUIVOS,
            "retencao_dias": settings.ESTOUROS_RETENCAO_DIAS,
            "recentes": LoteEstouro.objects.filter(user=request.user).prefetch_related("arquivos")[
                :LOTES_RECENTES
            ],
        }

    def get(self, request, pk=None):
        lote = _lote_do_usuario(request, pk) if pk else None
        inicial = None
        if lote:
            c = lote.configuracao
            inicial = {**c, "modo_tamanho": _modo_tamanho(c), "todos": c["topo"]}
            inicial.update({"horizontal": c["direita"], "vertical": c["topo"]})
        return render(
            request, self.template_name, self._contexto(request, EstouroForm(initial=inicial), lote)
        )

    def post(self, request, pk=None):
        form = EstouroForm(request.POST, request.FILES)
        if not form.is_valid():
            return render(request, self.template_name, self._contexto(request, form), status=400)
        lote = criar_lote(request.user, form)
        disparar(lote.pk)
        lote.refresh_from_db(fields=["status"])
        if lote.em_andamento:
            messages.info(request, "Arquivos enviados. Os estouros ficam prontos em instantes.")
        return redirect("estouros:lote", pk=lote.pk)


def _modo_tamanho(c: dict) -> str:
    if len({c["topo"], c["direita"], c["base"], c["esquerda"]}) == 1:
        return "igual"
    if c["topo"] == c["base"] and c["direita"] == c["esquerda"]:
        return "eixos"
    return "lados"


class LoteStatusView(LoginRequiredMixin, View):
    def get(self, request, pk):
        lote = LoteEstouro.objects.filter(pk=pk, user=request.user).first()
        if not lote:
            return JsonResponse({"erro": "nao_encontrado"}, status=404)
        return JsonResponse(
            {
                "status": lote.status,
                "status_display": lote.get_status_display(),
                "em_andamento": lote.em_andamento,
                "zip_url": reverse("estouros:baixar-zip", kwargs={"pk": lote.pk})
                if lote.zip_file
                else "",
                "arquivos": [
                    {
                        "id": a.pk,
                        "status": a.status,
                        "status_display": a.get_status_display(),
                        "erro": a.erro,
                    }
                    for a in lote.arquivos.all()
                ],
            }
        )


class BaixarArquivoView(LoginRequiredMixin, View):
    def get(self, request, pk):
        arquivo = (
            ArquivoEstouro.objects.filter(pk=pk, lote__user=request.user)
            .select_related("lote")
            .first()
        )
        if not arquivo or not arquivo.resultado:
            raise Http404
        return FileResponse(
            arquivo.resultado.open("rb"),
            as_attachment=True,
            filename=arquivo.nome_resultado,
            content_type="application/pdf",
        )


class PreviaArquivoView(LoginRequiredMixin, View):
    def get(self, request, pk):
        arquivo = ArquivoEstouro.objects.filter(pk=pk, lote__user=request.user).first()
        if not arquivo or not arquivo.previa:
            raise Http404
        return FileResponse(arquivo.previa.open("rb"), content_type="image/png")


class BaixarZipView(LoginRequiredMixin, View):
    def get(self, request, pk):
        lote = _lote_do_usuario(request, pk)
        if not lote.zip_file:
            raise Http404
        return FileResponse(
            lote.zip_file.open("rb"),
            as_attachment=True,
            filename=f"estouros-{lote.pk}.zip",
            content_type="application/zip",
        )


class ExcluirLoteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        lote = _lote_do_usuario(request, pk)
        lote.delete()
        messages.success(request, "Estouros excluídos.")
        return redirect("estouros:inicio")
