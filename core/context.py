from django.conf import settings

from .auth import ensure_user_profile, friendly_display_name
from .models import UserProfile


def app_shell(request):
    if not request.user.is_authenticated:
        return {}
    profile = ensure_user_profile(request.user)
    return {
        "app_role_label": profile.get_role_display(),
        "app_display_name": friendly_display_name(request.user),
        "is_visitor_user": profile.role == UserProfile.Role.VISITOR,
        "visitor_ttl_hours": settings.VISITOR_ACCOUNT_TTL_HOURS,
    }
