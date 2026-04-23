from django import forms
import pikepdf

from fonts.models import FontAsset

from .models import DocumentTemplate, TemplateField


class DocumentTemplateForm(forms.ModelForm):
    def clean_background_pdf(self):
        uploaded = self.cleaned_data["background_pdf"]
        suffix = uploaded.name.lower().rsplit(".", 1)[-1] if "." in uploaded.name else ""
        if suffix != "pdf":
            raise forms.ValidationError("Envie um arquivo PDF vetorial válido para o fundo.")
        uploaded.seek(0)
        try:
            pikepdf.Pdf.open(uploaded)
        except Exception as exc:
            uploaded.seek(0)
            raise forms.ValidationError("Não foi possível ler este PDF. Verifique se o arquivo não está corrompido.") from exc
        uploaded.seek(0)
        return uploaded

    class Meta:
        model = DocumentTemplate
        fields = ["name", "slug", "description", "background_pdf", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Certificado Base 2026"}),
            "slug": forms.TextInput(attrs={"placeholder": "certificado-base-2026"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Observações do template."}),
        }


class TemplateFieldForm(forms.ModelForm):
    class Meta:
        model = TemplateField
        fields = [
            "name",
            "label",
            "excel_column",
            "order_index",
            "page_number",
            "value_type",
            "x",
            "y",
            "width",
            "height",
            "font",
            "font_size",
            "is_bold",
            "is_italic",
            "text_align",
            "text_transform",
            "transform_exceptions",
            "color",
            "letter_spacing",
            "line_height",
            "max_lines",
            "integer_min_digits",
            "integer_keep_sign",
            "prefix",
            "suffix",
            "empty_value",
            "trim_whitespace",
            "overflow_mode",
            "preview_text",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "nome"}),
            "label": forms.TextInput(attrs={"placeholder": "Nome"}),
            "excel_column": forms.TextInput(attrs={"placeholder": "Coluna do Excel"}),
            "transform_exceptions": forms.TextInput(
                attrs={"placeholder": "de, da, do, dos, das, e, com"}
            ),
            "prefix": forms.TextInput(attrs={"placeholder": "Prefixo opcional"}),
            "suffix": forms.TextInput(attrs={"placeholder": "Sufixo opcional"}),
            "empty_value": forms.TextInput(attrs={"placeholder": "Valor quando vazio"}),
            "preview_text": forms.TextInput(attrs={"placeholder": "Texto de exemplo"}),
            "color": forms.TextInput(attrs={"placeholder": "#000000"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["font"].queryset = FontAsset.objects.filter(user=user, is_active=True).order_by("family", "variant")
