from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView

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
        status = self.request.GET.get("status", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(template__name__icontains=query))
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["status_filter"] = self.request.GET.get("status", "").strip()
        context["status_choices"] = GenerationJob.Status.choices
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


class GenerationJobDeleteView(UserOwnedQuerysetMixin, DeleteView):
    model = GenerationJob
    template_name = "jobs/job_confirm_delete.html"
    success_url = reverse_lazy("jobs:list")

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Job removido com sucesso.")
        return super().delete(request, *args, **kwargs)


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
