import io

import pikepdf
from django import forms
from django.core.files.base import ContentFile
from django.utils.text import slugify
from PIL import Image

from fonts.models import FontAsset

from .models import DocumentTemplate, TemplateField


IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "webp"}


def _image_to_pdf(uploaded, base_name: str) -> ContentFile:
    try:
        image = Image.open(uploaded)
        image.load()
    except Exception as exc:
        raise forms.ValidationError("Não foi possível ler esta imagem. Verifique se o arquivo não está corrompido.") from exc
    if image.mode in {"RGBA", "LA", "P"}:
        converted = image.convert("RGBA")
        background = Image.new("RGB", converted.size, (255, 255, 255))
        background.paste(converted, mask=converted.split()[-1])
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    buffer = io.BytesIO()
    # resolution=72 => 1 pixel da imagem vira 1 ponto na página do PDF.
    image.save(buffer, format="PDF", resolution=72.0)
    return ContentFile(buffer.getvalue(), name=f"{base_name}.pdf")


class DocumentTemplateForm(forms.ModelForm):
    def clean_background_pdf(self):
        uploaded = self.cleaned_data.get("background_pdf")
        if not uploaded:
            return self.instance.background_pdf
        name = uploaded.name.lower()
        suffix = name.rsplit(".", 1)[-1] if "." in name else ""
        if suffix in IMAGE_SUFFIXES:
            uploaded.seek(0)
            base_name = uploaded.name.rsplit(".", 1)[0].rsplit("/", 1)[-1] or "fundo"
            return _image_to_pdf(uploaded, base_name)
        if suffix != "pdf":
            raise forms.ValidationError("Envie um PDF, PNG, JPG ou WebP para o fundo do template.")
        uploaded.seek(0)
        try:
            with pikepdf.Pdf.open(uploaded) as pdf:
                if len(pdf.pages) != 1:
                    raise forms.ValidationError("O template deve ter exatamente 1 página.")
        except Exception as exc:
            uploaded.seek(0)
            if isinstance(exc, forms.ValidationError):
                raise
            raise forms.ValidationError("Não foi possível ler este PDF. Verifique se o arquivo não está corrompido.") from exc
        uploaded.seek(0)
        return uploaded

    def save(self, commit=True):
        instance = super().save(commit=False)
        base_slug = slugify(instance.name) or "template"
        slug = base_slug
        counter = 2
        while DocumentTemplate.objects.filter(user=instance.user, slug=slug).exclude(pk=instance.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        instance.slug = slug
        instance.page_count = 1
        if commit:
            instance.save()
        return instance

    class Meta:
        model = DocumentTemplate
        fields = ["name", "description", "background_pdf"]
        labels = {
            "name": "Nome",
            "description": "Descrição",
            "background_pdf": "Fundo (PDF, PNG, JPG ou WebP)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Certificado Base 2026"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Observações do template."}),
            "background_pdf": forms.FileInput(attrs={"accept": ".pdf,.png,.jpg,.jpeg,.webp"}),
        }


class TemplateFieldForm(forms.ModelForm):
    class Meta:
        model = TemplateField
        fields = [
            "name",
            "excel_column",
            "value_type",
            "font",
            "font_size",
            "text_align",
            "text_transform",
            "transform_exceptions",
            "color",
            "line_height",
            "max_lines",
            "integer_min_digits",
            "integer_keep_sign",
            "empty_value",
            "trim_whitespace",
            "overflow_mode",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "nome"}),
            "excel_column": forms.NumberInput(attrs={"placeholder": "1", "min": "1"}),
            "transform_exceptions": forms.TextInput(
                attrs={"placeholder": "de, da, do, dos, das, e, com"}
            ),
            "empty_value": forms.TextInput(attrs={"placeholder": "Valor quando vazio"}),
            "color": forms.TextInput(attrs={"placeholder": "#000000"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["font"].queryset = FontAsset.objects.filter(user=user, is_active=True).order_by("name")
