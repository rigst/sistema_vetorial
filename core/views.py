from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from editor.models import DocumentTemplate
from fonts.models import FontAsset
from jobs.models import GenerationJob


class HomeView(LoginRequiredMixin, TemplateView):
    template_name = "core/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context["template_count"] = DocumentTemplate.objects.filter(user=user).count()
        context["font_count"] = FontAsset.objects.filter(user=user, is_active=True).count()
        context["job_count"] = GenerationJob.objects.filter(user=user).count()
        context["recent_templates"] = DocumentTemplate.objects.filter(user=user)[:5]
        context["recent_jobs"] = GenerationJob.objects.filter(user=user)[:5]
        return context
