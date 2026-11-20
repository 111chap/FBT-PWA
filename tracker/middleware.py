from django.conf import settings


class SecurityHeaders:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.path.startswith(('/api/', '/login/', '/logout/', '/setup/', '/admin/')):
            response['Cache-Control'] = 'no-store, private'
        if request.path.startswith(('/api/', '/login/', '/setup/')) and request.user.is_authenticated:
            # Public account ID only, never an authentication credential. Lets the
            # offline client reject a previous account's copy after a login switch,
            # even if the network drops before the first new snapshot arrives.
            response.set_cookie('fbt_account_scope', str(request.user.pk), max_age=settings.SESSION_COOKIE_AGE,
                                secure=not settings.DEBUG, httponly=False, samesite='Strict')
        elif request.path == '/logout/':
            response.delete_cookie('fbt_account_scope', samesite='Strict')
        return response
