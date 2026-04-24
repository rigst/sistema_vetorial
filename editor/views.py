import json
from copy import deepcopy

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.text import slugify
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from core.mixins import UserOwnedQuerysetMixin
from fonts.models import FontAsset
from jobs.services import format_field_value

from .forms import DocumentTemplateForm
from .models import DocumentTemplate, TemplateField, TemplatePreviewPage
from .services import update_template_pdf_metadata


DEFAULT_EXCEPTIONS = "a, as, o, os, de, da, das, do, dos, e, em, com, para, por, na, nas, no, nos, à, às"


def field_to_dict(field: TemplateField) -> dict:
    return {
        "id": field.id,
        "name": field.name,
        "excel_column": field.excel_column,
        "value_type": field.value_type,
        "x": float(field.x),
        "y": float(field.y),
        "width": float(field.width),
        "height": float(field.height),
        "font_id": field.font_id,
        "font_name": field.font.name,
        "font_size": float(field.font_size),
        "text_align": field.text_align,
        "text_transform": field.text_transform,
        "transform_exceptions": field.transform_exceptions,
        "color": field.color,
        "border_enabled": field.border_enabled,
        "border_color": field.border_color,
        "border_size_ratio": float(field.border_size_ratio),
        "border_opacity": float(field.border_opacity),
        "border_blur": float(field.border_blur),
        "line_height": float(field.line_height),
        "max_lines": field.max_lines,
        "integer_min_digits": field.integer_min_digits,
        "integer_keep_sign": field.integer_keep_sign,
        "empty_value": field.empty_value,
        "trim_whitespace": field.trim_whitespace,
        "overflow_mode": field.overflow_mode,
        "preview_value": format_field_value(field, field.empty_value or field.name),
    }


def _parse_json_body(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise ValueError("Requisição inválida.")


def _next_excel_column(template_obj: DocumentTemplate) -> int:
    numeric_columns = []
    for value in template_obj.fields.values_list("excel_column", flat=True):
        try:
            numeric_columns.append(int(str(value).strip()))
        except (TypeError, ValueError):
            continue
    return (max(numeric_columns) if numeric_columns else 0) + 1


class DocumentTemplateListView(UserOwnedQuerysetMixin, ListView):
    model = DocumentTemplate
    template_name = "editor/template_list.html"
    context_object_name = "templates"
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        show_inactive = self.request.GET.get("inativos") == "1"
        queryset = queryset.filter(is_active=not show_inactive)
        if query:
            queryset = queryset.filter(name__icontains=query)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["show_inactive"] = self.request.GET.get("inativos") == "1"
        return context


class DocumentTemplateCreateView(LoginRequiredMixin, CreateView):
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = "editor/template_form.html"

    def form_valid(self, form):
        form.instance.user = self.request.user
        response = super().form_valid(form)
        try:
            update_template_pdf_metadata(self.object)
        except Exception:
            messages.error(self.request, "O template foi salvo, mas a pré-visualização do PDF não pôde ser gerada.")
        else:
            messages.success(self.request, "Template criado com sucesso.")
        return response

    def get_success_url(self):
        return reverse("editor:detail", kwargs={"pk": self.object.pk})


class DocumentTemplateUpdateView(UserOwnedQuerysetMixin, UpdateView):
    model = DocumentTemplate
    form_class = DocumentTemplateForm
    template_name = "editor/template_form.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.object.background_pdf:
            try:
                update_template_pdf_metadata(self.object)
            except Exception:
                messages.error(self.request, "As alterações foram salvas, mas a nova pré-visualização não pôde ser gerada.")
            else:
                messages.success(self.request, "Template atualizado com sucesso.")
        return response

    def get_success_url(self):
        return reverse("editor:detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_template_editor_context(self.object, self.request.user))
        context["is_template_form_page"] = True
        return context


def _template_editor_context(template_obj, user):
    fields = list(template_obj.fields.select_related("font").order_by("order_index", "id"))
    fonts = list(FontAsset.objects.filter(user=user, is_active=True).order_by("name"))
    return {
        "template_obj": template_obj,
        "preview_pages": template_obj.preview_pages.all(),
        "field_json": [field_to_dict(field) for field in fields],
        "font_options": fonts,
        "font_json": [{"id": font.id, "name": font.name} for font in fonts],
        "page_width_cm": round(float(template_obj.page_width or 0) * 2.54 / 72, 2) if template_obj.page_width else 0,
        "page_height_cm": round(float(template_obj.page_height or 0) * 2.54 / 72, 2) if template_obj.page_height else 0,
    }


class DocumentTemplateDetailView(UserOwnedQuerysetMixin, DetailView):
    model = DocumentTemplate
    template_name = "editor/template_detail.html"
    context_object_name = "template_obj"

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_template_editor_context(self.object, self.request.user))
        return context


class DocumentTemplatePreviewView(UserOwnedQuerysetMixin, TemplateView):
    template_name = "editor/template_preview.html"

    def dispatch(self, request, *args, **kwargs):
        self.template_obj = get_object_or_404(DocumentTemplate, pk=kwargs["pk"], user=request.user)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["template_obj"] = self.template_obj
        context["preview_pages"] = self.template_obj.preview_pages.all()
        context["field_json"] = [
            {**field_to_dict(field), "preview_value": format_field_value(field, field.empty_value or field.name)}
            for field in self.template_obj.fields.select_related("font").order_by("order_index", "id")
        ]
        return context


class DocumentTemplateDuplicateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        source = get_object_or_404(DocumentTemplate, pk=kwargs["pk"], user=request.user)
        clone_name = f"{source.name} Cópia"
        base_slug = slugify(clone_name) or "template-copia"
        clone_slug = base_slug
        counter = 2
        while DocumentTemplate.objects.filter(user=request.user, slug=clone_slug).exists():
            clone_slug = f"{base_slug}-{counter}"
            counter += 1
        with source.background_pdf.open("rb") as pdf_file:
            duplicated = DocumentTemplate.objects.create(
                user=request.user,
                name=clone_name,
                slug=clone_slug,
                description=source.description,
                background_pdf=ContentFile(pdf_file.read(), name=source.background_pdf.name.split("/")[-1]),
                page_width=source.page_width,
                page_height=source.page_height,
                page_count=1,
                editor_state=deepcopy(source.editor_state),
                is_active=True,
            )
        update_template_pdf_metadata(duplicated)
        for field in source.fields.all():
            field.pk = None
            field.template = duplicated
            field.save()
        messages.success(request, "Template duplicado com sucesso.")
        return redirect("editor:update", pk=duplicated.pk)


class DocumentTemplateDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        template_obj = get_object_or_404(DocumentTemplate, pk=kwargs["pk"], user=request.user)
        template_obj.is_active = False
        template_obj.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Template movido para inativos.")
        return redirect("editor:list")


class TemplateFieldsApiView(LoginRequiredMixin, View):
    def get_template(self, request, pk):
        return get_object_or_404(DocumentTemplate, pk=pk, user=request.user)

    def get(self, request, *args, **kwargs):
        template_obj = self.get_template(request, kwargs["pk"])
        data = [field_to_dict(field) for field in template_obj.fields.select_related("font").order_by("order_index", "id")]
        return JsonResponse({"fields": data})

    def post(self, request, *args, **kwargs):
        template_obj = self.get_template(request, kwargs["pk"])
        payload = _parse_json_body(request)
        name = (payload.get("name") or "").strip() or f"Campo {template_obj.fields.count() + 1}"
        font_id = payload.get("font_id")
        font = get_object_or_404(FontAsset, pk=font_id, user=request.user, is_active=True)
        order_index = template_obj.fields.count() + 1
        next_excel_column = _next_excel_column(template_obj)
        page_width = float(template_obj.page_width or 1200)
        page_height = float(template_obj.page_height or 300)
        width = round(page_width * 0.32, 2)
        height = round(page_height * 0.18, 2)
        center_x = round((page_width - width) / 2, 2)
        center_y = round((page_height - height) / 2, 2)
        field = TemplateField.objects.create(
            template=template_obj,
            name=name,
            excel_column=str(payload.get("excel_column") or next_excel_column),
            value_type=payload.get("value_type") or TemplateField.ValueType.TEXT,
            x=center_x,
            y=center_y,
            width=width,
            height=height,
            font=font,
            font_size=payload.get("font_size") or max(round(page_height * 0.09, 2), 28),
            text_align=payload.get("text_align") or TemplateField.TextAlign.CENTER,
            text_transform=payload.get("text_transform") or TemplateField.TextTransform.NONE,
            transform_exceptions=payload.get("transform_exceptions") or DEFAULT_EXCEPTIONS,
            color=payload.get("color") or "#000000",
            border_enabled=payload.get("border_enabled", False),
            border_color=payload.get("border_color") or "#000000",
            border_size_ratio=payload.get("border_size_ratio") or 0,
            border_opacity=payload.get("border_opacity") or 1,
            border_blur=payload.get("border_blur") or 0,
            line_height=payload.get("line_height") or 1.1,
            max_lines=payload.get("max_lines") or 1,
            integer_min_digits=payload.get("integer_min_digits") or 0,
            integer_keep_sign=payload.get("integer_keep_sign", True),
            empty_value=payload.get("empty_value") or name,
            trim_whitespace=True,
            overflow_mode=payload.get("overflow_mode") or TemplateField.OverflowMode.SHRINK,
            order_index=order_index,
            page_number=1,
        )
        return JsonResponse({"field": field_to_dict(field)}, status=201)


class TemplateFieldApiView(LoginRequiredMixin, View):
    def get_object(self, request, pk):
        return get_object_or_404(TemplateField.objects.select_related("template", "font"), pk=pk, template__user=request.user)

    def patch(self, request, *args, **kwargs):
        field = self.get_object(request, kwargs["pk"])
        payload = _parse_json_body(request)
        editable = {
            "name",
            "excel_column",
            "value_type",
            "x",
            "y",
            "width",
            "height",
            "font_size",
            "text_align",
            "text_transform",
            "transform_exceptions",
            "color",
            "border_enabled",
            "border_color",
            "border_size_ratio",
            "border_opacity",
            "border_blur",
            "line_height",
            "max_lines",
            "integer_min_digits",
            "integer_keep_sign",
            "empty_value",
            "trim_whitespace",
            "overflow_mode",
        }
        update_fields = ["updated_at"]
        for key, value in payload.items():
            if key not in editable:
                continue
            setattr(field, key, value)
            update_fields.append(key)
        if "font_id" in payload:
            field.font = get_object_or_404(FontAsset, pk=payload["font_id"], user=request.user, is_active=True)
            update_fields.append("font")
        field.page_number = 1
        if "page_number" not in update_fields:
            update_fields.append("page_number")
        field.save(update_fields=update_fields)
        return JsonResponse({"field": field_to_dict(field)})

    def delete(self, request, *args, **kwargs):
        field = self.get_object(request, kwargs["pk"])
        field.delete()
        return JsonResponse({"ok": True})


class TemplateLayoutUpdateView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        template_obj = get_object_or_404(DocumentTemplate, pk=kwargs["pk"], user=request.user)
        payload = _parse_json_body(request)
        updates = payload.get("fields", [])
        for item in updates:
            field = get_object_or_404(TemplateField, pk=item["id"], template=template_obj)
            field.x = item["x"]
            field.y = item["y"]
            field.width = item["width"]
            field.height = item["height"]
            field.page_number = 1
            field.save(update_fields=["x", "y", "width", "height", "page_number", "updated_at"])
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
