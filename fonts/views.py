from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from core.mixins import UserOwnedQuerysetMixin

from .forms import FontAssetForm
from .models import FontAsset


class FontAssetListView(UserOwnedQuerysetMixin, ListView):
    model = FontAsset
    template_name = "fonts/fontasset_list.html"
    context_object_name = "fonts"
    paginate_by = 12

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q", "").strip()
        show_inactive = self.request.GET.get("inativos") == "1"
        queryset = queryset.filter(is_active=not show_inactive)
        if query:
            queryset = queryset.filter(Q(name__icontains=query))
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["query"] = self.request.GET.get("q", "").strip()
        context["show_inactive"] = self.request.GET.get("inativos") == "1"
        return context


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


class FontAssetDeleteView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        font = FontAsset.objects.filter(pk=kwargs["pk"], user=request.user).first()
        if font:
            font.is_active = False
            font.save(update_fields=["is_active", "updated_at"])
            messages.success(request, "Fonte movida para inativas.")
        return redirect("fonts:list")
