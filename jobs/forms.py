from django import forms

from editor.models import DocumentTemplate

from .models import GenerationJob


class GenerationJobForm(forms.ModelForm):
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
