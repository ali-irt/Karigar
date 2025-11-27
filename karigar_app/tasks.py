from celery import shared_task
from .models import ServiceRequest
from django.utils import timezone
from datetime import timedelta

@shared_task
def cleanup_expired_pending_requests():
    """
    Celery task to periodically clean up ServiceRequests that have been pending
    for longer than the allowed time (30 seconds).
    """
    # NOTE: The timeout is hardcoded to 30 seconds as per user request.
    timeout_seconds = 30
    
    deleted_count = ServiceRequest.objects.delete_expired_pending_requests(timeout_seconds)
    
    if deleted_count > 0:
        print(f"[{timezone.now()}] Cleaned up {deleted_count} expired pending ServiceRequests.")
    
    return f"Cleaned up {deleted_count} expired pending ServiceRequests."

# NOTE: The original content of tasks.py seemed to be a copy of urls.py.
# I have replaced it with the intended Celery task definition.
# If you are not using Celery, you will need to adapt this to your chosen task runner.