import datetime
import logging
from typing import TYPE_CHECKING, Union

from django.conf import settings

from .jwt import JWT_REFRESH_TOKEN_COOKIE_NAME, jwt_decode_with_exception_handler

if TYPE_CHECKING:
    from ..account.models import User
    from ..app.models import App

Requestor = Union["User", "App"]

logger = logging.getLogger(__name__)


def jwt_refresh_token_middleware(get_response):
    def middleware(request):
        """Append generated refresh_token to response object."""
        response = get_response(request)
        jwt_refresh_token = getattr(request, "refresh_token", None)
        if jwt_refresh_token:
            expires = None
            secure = not settings.DEBUG
            if settings.JWT_EXPIRE:
                refresh_token_payload = jwt_decode_with_exception_handler(
                    jwt_refresh_token
                )
                if refresh_token_payload and refresh_token_payload.get("exp"):
                    expires = datetime.datetime.fromtimestamp(
                        refresh_token_payload["exp"], tz=datetime.UTC
                    )
            response.set_cookie(
                JWT_REFRESH_TOKEN_COOKIE_NAME,
                jwt_refresh_token,
                expires=expires,
                httponly=True,  # protects token from leaking
                secure=secure,
                samesite="None" if secure else "Lax",
            )
        return response

    return middleware




import json
import sys

class GraphQLLogger:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/graphql/" and request.method == "POST":
            try:
                body = request.body.decode("utf-8")
                print(">>> GRAPHQL REQUEST", body, flush=True, file=sys.stderr)
            except Exception as e:
                print("Decode error:", e, flush=True, file=sys.stderr)

        response = self.get_response(request)

        if request.path == "/graphql/" and hasattr(response, "content"):
            try:
                data = response.content.decode("utf-8")
                print(">>> GRAPHQL RESPONSE", data[:500], flush=True, file=sys.stderr)
            except Exception:
                pass

        return response