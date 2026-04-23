from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import UserOwnedQuerysetMixin

from .forms import FontAssetForm
from .models import FontAsset


class FontAssetListView(UserOwnedQuerysetMixin, ListView):
    model = FontAsset
    template_name = "fonts/fontasset_list.html"
    context_object_name = "fonts"


class FontAssetCreateView(LoginRequiredMixin, CreateView):
    model = FontAsset
    form_class = FontAssetForm
    template_name = "fonts/fontasset_form.html"
    success_url = reverse_lazy("fonts:list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class FontAssetUpdateView(UserOwnedQuerysetMixin, UpdateView):
    model = FontAsset
    form_class = FontAssetForm
    template_name = "fonts/fontasset_form.html"
    success_url = reverse_lazy("fonts:list")
