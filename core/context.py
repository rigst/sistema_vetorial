from .auth import ensure_user_profile
from .models import UserProfile


def app_shell(request):
    if not request.user.is_authenticated:
        return {}
    profile = ensure_user_profile(request.user)
    return {
        "app_role_label": profile.get_role_display(),
        "app_display_name": request.user.first_name
        or request.user.get_full_name()
        or request.user.username,
        "is_visitor_user": profile.role == UserProfile.Role.VISITOR,
    }
