from django.contrib.auth.mixins import LoginRequiredMixin


class UserOwnedQuerysetMixin(LoginRequiredMixin):
    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.user = self.request.user
        return super().form_valid(form)
