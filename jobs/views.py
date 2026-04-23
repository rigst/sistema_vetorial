from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView
from django.core.files.base import ContentFile

from core.mixins import UserOwnedQuerysetMixin
from django.conf import settings

from .forms import GenerationJobForm
from .models import GenerationJob
from .runner import spawn_job_process


class GenerationJobListView(UserOwnedQuerysetMixin, ListView):
    model = GenerationJob
    template_name = "jobs/job_list.html"
    context_object_name = "jobs"


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
        spawn_job_process(settings.BASE_DIR, self.object.pk)
        messages.success(self.request, "Job enviado para processamento.")
        return response

    def get_success_url(self):
        return reverse("jobs:detail", kwargs={"pk": self.object.pk})


class GenerationJobDetailView(UserOwnedQuerysetMixin, DetailView):
    model = GenerationJob
    template_name = "jobs/job_detail.html"
    context_object_name = "job"


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
        spawn_job_process(settings.BASE_DIR, full_job.pk)
        messages.success(request, "Lote completo enviado para processamento.")
        return redirect("jobs:detail", pk=full_job.pk)


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
                "zip_url": job.zip_file.url if job.zip_file else "",
                "items": [
                    {
                        "row_number": item.row_number,
                        "status": item.status,
                        "status_display": item.get_status_display(),
                        "error_message": item.error_message,
                        "output_url": item.output_pdf.url if item.output_pdf else "",
                    }
                    for item in job.items.order_by("row_number")
                ],
            }
        )
