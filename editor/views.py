import json
from copy import deepcopy

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.files.base import ContentFile
from django.http import FileResponse
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.utils.text import slugify
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.mixins import UserOwnedQuerysetMixin

from .forms import DocumentTemplateForm, TemplateFieldForm
from .models import DocumentTemplate, TemplateField, TemplatePreviewPage
from .services import update_template_pdf_metadata
from jobs.services import format_field_value, get_missing_font_chars, load_excel_rows


class DocumentTemplateListView(UserOwnedQuerysetMixin, ListView):
    model = DocumentTemplate
    template_name = "editor/template_list.html"
    context_object_name = "templates"
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query) | Q(slug__icontains=query))
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["status_filter"] = self.request.GET.get("status", "").strip()
        context["status_choices"] = DocumentTemplate.Status.choices
        return context


class DocumentTemplateCreateView(LoginRequiredMixin, CreateView):
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = "editor/template_form.html"
    success_url = reverse_lazy("editor:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        try:
            update_template_pdf_metadata(self.object)
        except Exception:
            messages.error(
                self.request,
                "O template foi salvo, mas não foi possível gerar a prévia do PDF. Verifique se o arquivo é válido e tente novamente.",
            )
        return response


class DocumentTemplateUpdateView(UserOwnedQuerysetMixin, UpdateView):
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = "editor/template_form.html"
    success_url = reverse_lazy("editor:list")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.object.background_pdf:
            try:
                update_template_pdf_metadata(self.object)
            except Exception:
                messages.error(
                    self.request,
                    "As alterações foram salvas, mas a nova prévia do PDF não pôde ser atualizada. Revise o arquivo enviado.",
                )
        return response


class DocumentTemplateDetailView(UserOwnedQuerysetMixin, DetailView):
    model = DocumentTemplate
    template_name = "editor/template_detail.html"
    context_object_name = "template_obj"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        sample_payload = {}
        sample_job = self.object.jobs.order_by("-created_at").first()
        if sample_job and sample_job.source_excel:
            try:
                _, data_rows = load_excel_rows(sample_job.source_excel.path)
            except Exception:
                data_rows = []
            if data_rows:
                sample_payload = data_rows[0][1]
        field_previews = []
        for field in self.object.fields.select_related("font").all():
            sample_source = (
                sample_payload.get(field.excel_column)
                or field.preview_text
                or field.empty_value
                or field.label
            )
            rendered_preview = format_field_value(field, sample_source)
            missing_chars = get_missing_font_chars(field, rendered_preview)
            field_previews.append(
                {
                    "field": field,
                    "sample_source": sample_source,
                    "rendered_preview": rendered_preview,
                    "missing_chars": missing_chars,
                }
            )
        context["field_layout_json"] = [
            {
                "id": field.id,
                "label": field.label,
                "excel_column": field.excel_column,
                "page_number": field.page_number,
                "x": float(field.x),
                "y": float(field.y),
                "width": float(field.width),
                "height": float(field.height),
                "font_size": float(field.font_size),
            }
            for field in self.object.fields.all()
        ]
        context["preview_pages"] = self.object.preview_pages.all()
        context["field_previews"] = field_previews
        context["font_warning_count"] = sum(1 for item in field_previews if item["missing_chars"])
        context["sample_job"] = sample_job
        context["sample_payload"] = sample_payload
        return context


class DocumentTemplateDuplicateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        source = get_object_or_404(DocumentTemplate, pk=kwargs["pk"], user=request.user)
        base_slug = slugify(f"{source.slug}-copia")
        next_version = source.version + 1
        new_slug = f"{base_slug}-v{next_version}"
        while DocumentTemplate.objects.filter(user=request.user, slug=new_slug, version=next_version).exists():
            next_version += 1
            new_slug = f"{base_slug}-v{next_version}"

        with source.background_pdf.open("rb") as pdf_file:
            duplicated = DocumentTemplate.objects.create(
                user=request.user,
                name=f"{source.name} (Cópia)",
                slug=new_slug,
                description=source.description,
                background_pdf=ContentFile(
                    pdf_file.read(),
                    name=source.background_pdf.name.split("/")[-1],
                ),
                status=DocumentTemplate.Status.DRAFT,
                page_width=source.page_width,
                page_height=source.page_height,
                page_count=source.page_count,
                version=next_version,
                editor_state=deepcopy(source.editor_state),
            )

        try:
            update_template_pdf_metadata(duplicated)
        except Exception:
            messages.warning(
                request,
                "O template foi duplicado, mas a prévia visual não pôde ser regenerada agora.",
            )
        for field in source.fields.all():
            field.pk = None
            field.template = duplicated
            field.save()

        messages.success(request, "Template duplicado com sucesso.")
        return redirect("editor:detail", pk=duplicated.pk)


class DocumentTemplateDeleteView(UserOwnedQuerysetMixin, DeleteView):
    model = DocumentTemplate
    success_url = reverse_lazy("editor:list")
    template_name = "editor/template_confirm_delete.html"

    def delete(self, request, *args, **kwargs):
        messages.success(request, "Template removido com sucesso.")
        return super().delete(request, *args, **kwargs)


class TemplateFieldCreateView(LoginRequiredMixin, CreateView):
    model = TemplateField
    form_class = TemplateFieldForm
    template_name = "editor/field_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.template_obj = get_object_or_404(DocumentTemplate, pk=kwargs["template_pk"], user=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.template = self.template_obj
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("editor:detail", kwargs={"pk": self.template_obj.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["template_obj"] = self.template_obj
        return context


class TemplateFieldUpdateView(UserOwnedQuerysetMixin, UpdateView):
    model = TemplateField
    form_class = TemplateFieldForm
    template_name = "editor/field_form.html"

    def get_queryset(self):
        return super().get_queryset().filter(template__user=self.request.user).select_related("template")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_success_url(self):
        return reverse("editor:detail", kwargs={"pk": self.object.template_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["template_obj"] = self.object.template
        return context


class TemplateFieldDeleteView(UserOwnedQuerysetMixin, DeleteView):
    model = TemplateField
    template_name = "editor/field_confirm_delete.html"

    def get_queryset(self):
        return super().get_queryset().filter(template__user=self.request.user).select_related("template")

    def get_success_url(self):
        messages.success(self.request, "Campo removido com sucesso.")
        return reverse("editor:detail", kwargs={"pk": self.object.template_id})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["template_obj"] = self.object.template
        return context


class TemplateLayoutUpdateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        template_obj = get_object_or_404(DocumentTemplate, pk=kwargs["pk"], user=request.user)
        payload = json.loads(request.body.decode("utf-8"))
        updates = payload.get("fields", [])

        for item in updates:
            field = get_object_or_404(TemplateField, pk=item["id"], template=template_obj)
            field.x = item["x"]
            field.y = item["y"]
            field.width = item["width"]
            field.height = item["height"]
            field.save(update_fields=["x", "y", "width", "height", "updated_at"])

        return JsonResponse({"ok": True, "updated": len(updates)})


class TemplatePreviewPageImageView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        preview_page = get_object_or_404(
            TemplatePreviewPage,
            template_id=kwargs["pk"],
            page_number=kwargs["page_number"],
            template__user=request.user,
        )
        return FileResponse(preview_page.image.open("rb"), content_type="image/png")
