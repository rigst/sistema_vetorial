from pathlib import Path

from django import forms

from .models import FontAsset
from .services import inspect_font_file


class FontAssetForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = False

    class Meta:
        model = FontAsset
        fields = ["name", "file"]
        labels = {
            "name": "Nome",
            "file": "Arquivo (TTF ou OTF)",
        }
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Nome da fonte"}),
            # FileInput, não ClearableFileInput: o widget "clearable" tenta
            # montar um link "Arquivo atual: <a href=file.url>" ao editar, e
            # o Storage privado (core/storage.py) recusa gerar essa URL de
            # propósito — o formulário de edição quebrava com 500 nisso.
            "file": forms.FileInput(attrs={"accept": ".ttf,.otf"}),
        }
        help_texts = {
            "name": "Deixe em branco para usar o nome do arquivo.",
        }

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        suffix = uploaded.name.lower().rsplit(".", 1)[-1] if "." in uploaded.name else ""
        if suffix not in {"ttf", "otf"}:
            raise forms.ValidationError("Envie uma fonte TTF ou OTF.")
        uploaded.seek(0)
        temp_path = None
        try:
            source_path = (
                uploaded.temporary_file_path()
                if hasattr(uploaded, "temporary_file_path")
                else self._persist_temp_file(uploaded)
            )
            temp_path = None if hasattr(uploaded, "temporary_file_path") else source_path
            metadata = inspect_font_file(source_path)
        except Exception as exc:
            raise forms.ValidationError(
                "Não foi possível ler esta fonte. Verifique se o arquivo TTF/OTF está íntegro."
            ) from exc
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
            uploaded.seek(0)
        self._font_metadata = metadata
        return uploaded

    def _persist_temp_file(self, uploaded):
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(
            delete=False, suffix=f".{uploaded.name.rsplit('.', 1)[-1]}"
        ) as temp:
            for chunk in uploaded.chunks():
                temp.write(chunk)
            return temp.name

    def clean(self):
        cleaned = super().clean() or {}
        if not cleaned.get("name") and cleaned.get("file"):
            metadata = getattr(self, "_font_metadata", None)
            # O nome que a própria fonte declara ("DejaVu Sans Bold") é mais
            # confiável que adivinhar a partir do nome do arquivo — só cai
            # para o nome do arquivo quando a fonte não informa nada.
            full_name = metadata.get("full_name") if metadata else ""
            cleaned["name"] = full_name or (
                Path(cleaned["file"].name).stem.replace("_", " ").replace("-", " ").title()
            )
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        metadata = getattr(self, "_font_metadata", None)
        if metadata:
            instance.metadata = metadata
            # Família e peso vêm do próprio arquivo (tabelas name/OS2): é o
            # que permite que Regular e Bold da mesma fonte apareçam juntos,
            # agrupados, em vez de virarem duas fontes "família" distintas.
            instance.family = metadata.get("detected_family") or instance.name
            instance.variant = metadata.get("detected_variant") or "Regular"
            instance.weight = metadata.get("weight") or 400
            instance.is_italic = bool(metadata.get("is_italic"))
        else:
            instance.family = instance.name
        instance.is_active = True
        if commit:
            instance.save()
        return instance
