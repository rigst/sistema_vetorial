from django import forms

from fonts.models import FontAsset

from .models import DocumentTemplate, TemplateField


class DocumentTemplateForm(forms.ModelForm):
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
            "x",
            "y",
            "width",
            "height",
            "font",
            "font_size",
            "is_bold",
            "is_italic",
            "text_align",
            "color",
            "letter_spacing",
            "line_height",
            "max_lines",
            "overflow_mode",
            "preview_text",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "nome"}),
            "label": forms.TextInput(attrs={"placeholder": "Nome"}),
            "excel_column": forms.TextInput(attrs={"placeholder": "Coluna do Excel"}),
            "preview_text": forms.TextInput(attrs={"placeholder": "Texto de exemplo"}),
            "color": forms.TextInput(attrs={"placeholder": "#000000"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["font"].queryset = FontAsset.objects.filter(user=user, is_active=True).order_by("family", "variant")
