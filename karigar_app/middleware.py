# myapp/middleware.py
import time
from django.utils.deprecation import MiddlewareMixin

class ResponseTimeMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.start_time = time.time()

    def process_response(self, request, response):
        if hasattr(request, 'start_time'):
            duration = (time.time() - request.start_time) * 1000  # in ms
            # Add to response headers
            response['X-Response-Time-ms'] = f'{duration:.2f}'
        return response
