from django import forms

from .models import FontAsset


class FontAssetForm(forms.ModelForm):
    class Meta:
        model = FontAsset
        fields = ["name", "family", "variant", "file", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Ex.: Gotham Bold"}),
            "family": forms.TextInput(attrs={"placeholder": "Ex.: Gotham"}),
        }
