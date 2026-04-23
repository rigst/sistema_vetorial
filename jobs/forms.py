from django import forms
from openpyxl import load_workbook

from editor.models import DocumentTemplate

from .models import GenerationJob


class GenerationJobForm(forms.ModelForm):
    def clean_source_excel(self):
        uploaded = self.cleaned_data["source_excel"]
        suffix = uploaded.name.lower().rsplit(".", 1)[-1] if "." in uploaded.name else ""
        if suffix not in {"xlsx", "xlsm"}:
            raise forms.ValidationError("Envie um arquivo Excel .xlsx ou .xlsm.")
        uploaded.seek(0)
        try:
            workbook = load_workbook(uploaded, read_only=True, data_only=True)
            sheet = workbook.active
            rows = list(sheet.iter_rows(values_only=True, max_row=2))
            workbook.close()
        except Exception as exc:
            uploaded.seek(0)
            raise forms.ValidationError("Não foi possível ler o Excel. Verifique se o arquivo está íntegro e com formato válido.") from exc
        finally:
            uploaded.seek(0)

        if not rows or not rows[0]:
            raise forms.ValidationError("O Excel precisa ter uma primeira linha de cabeçalho.")

        headers = [str(value).strip() if value is not None else "" for value in rows[0]]
        if not any(headers):
            raise forms.ValidationError("A primeira linha do Excel está vazia. Informe um cabeçalho válido.")
        self._uploaded_headers = headers
        return uploaded

    class Meta:
        model = GenerationJob
        fields = ["name", "template", "source_excel"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Lote abril 2026"}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        template_id = kwargs.pop("template_id", None)
        super().__init__(*args, **kwargs)
        self.fields["template"].queryset = DocumentTemplate.objects.filter(user=user).order_by("name")
        if template_id:
            self.fields["template"].initial = template_id

    def clean(self):
        cleaned = super().clean()
        template = cleaned.get("template")
        headers = getattr(self, "_uploaded_headers", None)
        if template and headers:
            expected = [field.excel_column for field in template.fields.all() if field.excel_column]
            missing = [header for header in expected if header not in headers]
            if missing:
                raise forms.ValidationError(
                    "O Excel não possui todos os cabeçalhos esperados pelo template. Faltando: "
                    + ", ".join(missing)
                )
        return cleaned
