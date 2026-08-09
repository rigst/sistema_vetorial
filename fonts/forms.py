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
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Nome da fonte"}),
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
        cleaned = super().clean()
        if not cleaned.get("name") and cleaned.get("file"):
            cleaned["name"] = (
                Path(cleaned["file"].name).stem.replace("_", " ").replace("-", " ").title()
            )
        metadata = getattr(self, "_font_metadata", None)
        if metadata and not cleaned.get("name") and metadata.get("full_name"):
            cleaned["name"] = metadata["full_name"]
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        metadata = getattr(self, "_font_metadata", None)
        if metadata:
            instance.metadata = metadata
        instance.family = instance.name
        instance.variant = FontAsset.Variant.REGULAR
        instance.is_active = True
        if commit:
            instance.save()
        return instance
