from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView

from core.mixins import UserOwnedQuerysetMixin
from django.conf import settings
from editor.models import DocumentTemplate

from .forms import GenerationJobForm
from .models import GenerationItem, GenerationJob
from .runner import spawn_job_process


class GenerationJobListView(UserOwnedQuerysetMixin, ListView):
    model = GenerationJob
    template_name = "jobs/job_list.html"
    context_object_name = "jobs"
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset().select_related("template")
        query = self.request.GET.get("q", "").strip()
        show_inactive = self.request.GET.get("inativos") == "1"
        queryset = queryset.filter(is_active=not show_inactive)
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(template__name__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["show_inactive"] = self.request.GET.get("inativos") == "1"
        return context


class GenerationJobCreateView(LoginRequiredMixin, CreateView):
    model = GenerationJob
    form_class = GenerationJobForm
    template_name = "jobs/job_form.html"
    success_url = reverse_lazy("jobs:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        kwargs["template_id"] = self.request.GET.get("template")
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        form.instance.kind = (
            GenerationJob.Kind.FULL if "generate_full" in self.request.POST else GenerationJob.Kind.PREVIEW
        )
        form.instance.status = GenerationJob.Status.QUEUED
        response = super().form_valid(form)
        try:
            spawn_job_process(settings.BASE_DIR, self.object.pk)
        except Exception:
            self.object.status = GenerationJob.Status.FAILED
            self.object.last_error = (
                "O job foi salvo, mas não foi possível iniciar o processamento automático. Tente reenviar o job."
            )
            self.object.save(update_fields=["status", "last_error", "updated_at"])
            messages.error(self.request, self.object.last_error)
        else:
            messages.success(self.request, "Job enviado para processamento.")
        return response

    def get_success_url(self):
        return reverse("jobs:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        template_id = self.request.GET.get("template") or self.request.POST.get("template")
        template_obj = None
        if template_id:
            template_obj = DocumentTemplate.objects.filter(pk=template_id, user=self.request.user).prefetch_related("fields").first()
        context["selected_template"] = template_obj
        context["expected_headers"] = [field.excel_column for field in template_obj.fields.all() if field.excel_column] if template_obj else []
        return context


class GenerationJobDetailView(UserOwnedQuerysetMixin, DetailView):
    model = GenerationJob
    template_name = "jobs/job_detail.html"
    context_object_name = "job"


class GenerationJobDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        job = GenerationJob.objects.filter(pk=kwargs["pk"], user=request.user).first()
        if job:
            job.is_active = False
            job.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Job movido para inativos.")
        return redirect("jobs:list")


class PromotePreviewJobView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        preview_job = GenerationJob.objects.filter(
            pk=kwargs["pk"], user=request.user, kind=GenerationJob.Kind.PREVIEW
        ).select_related("template").first()
        if not preview_job:
            messages.error(request, "Prévia não encontrada.")
            return redirect("jobs:list")

        with preview_job.source_excel.open("rb") as source_file:
            full_job = GenerationJob.objects.create(
                user=preview_job.user,
                template=preview_job.template,
                name=f"{preview_job.name} - lote completo",
                source_excel=ContentFile(
                    source_file.read(),
                    name=preview_job.source_excel.name.split("/")[-1],
                ),
                kind=GenerationJob.Kind.FULL,
                status=GenerationJob.Status.QUEUED,
            )
        try:
            spawn_job_process(settings.BASE_DIR, full_job.pk)
        except Exception:
            full_job.status = GenerationJob.Status.FAILED
            full_job.last_error = (
                "O lote completo foi criado, mas não foi possível iniciar o processamento automático."
            )
            full_job.save(update_fields=["status", "last_error", "updated_at"])
            messages.error(request, full_job.last_error)
        else:
            messages.success(request, "Lote completo enviado para processamento.")
        return redirect("jobs:detail", pk=full_job.pk)


class RerunJobView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        source_job = GenerationJob.objects.filter(pk=kwargs["pk"], user=request.user).select_related("template").first()
        if not source_job:
            messages.error(request, "Job não encontrado.")
            return redirect("jobs:list")

        with source_job.source_excel.open("rb") as source_file:
            new_job = GenerationJob.objects.create(
                user=request.user,
                template=source_job.template,
                name=f"{source_job.name} - reprocessado",
                source_excel=ContentFile(
                    source_file.read(),
                    name=source_job.source_excel.name.split("/")[-1],
                ),
                kind=source_job.kind,
                status=GenerationJob.Status.QUEUED,
            )
        try:
            spawn_job_process(settings.BASE_DIR, new_job.pk)
        except Exception:
            new_job.status = GenerationJob.Status.FAILED
            new_job.last_error = "O job foi recriado, mas o processamento automático não pôde ser iniciado."
            new_job.save(update_fields=["status", "last_error", "updated_at"])
            messages.error(request, new_job.last_error)
        else:
            messages.success(request, "Job reenviado para processamento.")
        return redirect("jobs:detail", pk=new_job.pk)


class GenerationJobStatusView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        job = GenerationJob.objects.filter(pk=kwargs["pk"], user=request.user).first()
        if not job:
            return JsonResponse({"error": "not_found"}, status=404)

        return JsonResponse(
            {
                "status": job.status,
                "status_display": job.get_status_display(),
                "kind": job.kind,
                "total_rows": job.total_rows,
                "processed_rows": job.processed_rows,
                "success_rows": job.success_rows,
                "failed_rows": job.failed_rows,
                "last_error": job.last_error,
                "zip_url": reverse("jobs:download-zip", kwargs={"pk": job.pk}) if job.zip_file else "",
                "items": [
                    {
                        "row_number": item.row_number,
                        "status": item.status,
                        "status_display": item.get_status_display(),
                        "error_message": item.error_message,
                        "output_url": reverse("jobs:download-item", kwargs={"pk": item.pk}) if item.output_pdf else "",
                    }
                    for item in job.items.order_by("row_number")
                ],
            }
        )


class GenerationJobZipDownloadView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        job = GenerationJob.objects.filter(pk=kwargs["pk"], user=request.user).first()
        if not job or not job.zip_file:
            return JsonResponse({"error": "not_found"}, status=404)
        return FileResponse(job.zip_file.open("rb"), as_attachment=True, filename=job.zip_file.name.split("/")[-1])


class GenerationJobSourceExcelDownloadView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        job = GenerationJob.objects.filter(pk=kwargs["pk"], user=request.user).first()
        if not job or not job.source_excel:
            return JsonResponse({"error": "not_found"}, status=404)
        return FileResponse(
            job.source_excel.open("rb"),
            as_attachment=True,
            filename=job.source_excel.name.split("/")[-1],
        )


class GenerationItemDownloadView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        item = GenerationItem.objects.filter(pk=kwargs["pk"], job__user=request.user).select_related("job").first()
        if not item or not item.output_pdf:
            return JsonResponse({"error": "not_found"}, status=404)
        return FileResponse(item.output_pdf.open("rb"), as_attachment=True, filename=item.output_pdf.name.split("/")[-1])


class GenerationJobLaunchApiView(LoginRequiredMixin, View):
    """Cria e dispara um job direto da bancada do projeto (AJAX)."""

    def post(self, request, *args, **kwargs):
        template_obj = DocumentTemplate.objects.filter(
            pk=request.POST.get("template"), user=request.user, is_active=True
        ).first()
        if not template_obj:
            return JsonResponse({"error": "Projeto não encontrado."}, status=404)
        if not template_obj.fields.exists():
            return JsonResponse({"error": "Crie ao menos um campo antes de gerar os arquivos."}, status=400)

        kind = request.POST.get("kind")
        if kind not in {GenerationJob.Kind.PREVIEW, GenerationJob.Kind.FULL}:
            return JsonResponse({"error": "Tipo de geração inválido."}, status=400)

        form = GenerationJobForm(
            data={
                "name": (request.POST.get("name") or "").strip()
                or f"{template_obj.name} · {timezone.localtime():%d/%m %H:%M}",
                "template": template_obj.pk,
            },
            files={"source_excel": request.FILES.get("source_excel")},
            user=request.user,
        )
        if not form.is_valid():
            first_error = next(iter(form.errors.values()))[0]
            return JsonResponse({"error": first_error}, status=400)

        job = form.save(commit=False)
        job.user = request.user
        job.kind = kind
        job.status = GenerationJob.Status.QUEUED
        job.save()
        try:
            spawn_job_process(settings.BASE_DIR, job.pk)
        except Exception:
            job.status = GenerationJob.Status.FAILED
            job.last_error = "O job foi salvo, mas o processamento automático não pôde ser iniciado."
            job.save(update_fields=["status", "last_error", "updated_at"])
        return JsonResponse(
            {
                "id": job.pk,
                "status": job.status,
                "status_url": reverse("jobs:status", kwargs={"pk": job.pk}),
            },
            status=201,
        )
