import pikepdf
from django import forms
from django.utils.text import slugify

from fonts.models import FontAsset

from .models import DocumentTemplate, TemplateField


class DocumentTemplateForm(forms.ModelForm):
    def clean_background_pdf(self):
        uploaded = self.cleaned_data.get("background_pdf")
        if not uploaded:
            return self.instance.background_pdf
        suffix = uploaded.name.lower().rsplit(".", 1)[-1] if "." in uploaded.name else ""
        if suffix != "pdf":
            raise forms.ValidationError("Envie um arquivo PDF vetorial válido para o fundo.")
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
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Certificado Base 2026"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Observações do template."}),
            "background_pdf": forms.FileInput(),
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
