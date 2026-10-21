"""Compress negotiated market JSON only; leave MCP/SSE and other routes alone."""
from starlette.middleware.gzip import GZipMiddleware


class ResearchCompressionMiddleware:
    def __init__(self, app):
        self.app = app
        self.compressed = GZipMiddleware(app, minimum_size=1000, compresslevel=1)

    async def __call__(self, scope, receive, send):
        target = self.compressed if (scope['type'] == 'http' and
            scope.get('method') == 'POST' and scope.get('path') == '/v1/research/market') else self.app
        await target(scope, receive, send)
