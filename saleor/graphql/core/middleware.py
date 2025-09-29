




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