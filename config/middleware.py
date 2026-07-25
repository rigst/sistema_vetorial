from django.conf import settings


class SecurityHeadersMiddleware:
    """Cabeçalhos de segurança, com uma CSP própria para o /admin/.

    O app público mantém a política estrita. O admin não cabe nela porque o
    tema (django-unfold) usa Alpine.js, que avalia as expressões dos atributos
    `x-data`/`x-init` via `new Function()` e portanto exige 'unsafe-eval' — que
    o 'unsafe-inline' da política pública não cobre. Em vez de afrouxar o site
    inteiro por causa do painel, a exceção fica restrita ao prefixo do admin,
    que já é acessível apenas a `is_staff`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def _politica(self, request):
        prefixo = getattr(settings, "ADMIN_PATH_PREFIX", "/admin/")
        if request.path.startswith(prefixo):
            return (
                getattr(settings, "CONTENT_SECURITY_POLICY_ADMIN", "")
                or getattr(settings, "CONTENT_SECURITY_POLICY", "")
            )
        return getattr(settings, "CONTENT_SECURITY_POLICY", "")

    def __call__(self, request):
        response = self.get_response(request)
        csp = self._politica(request)
        if csp:
            response.setdefault("Content-Security-Policy", csp)
        response.setdefault("Referrer-Policy", "same-origin")
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
