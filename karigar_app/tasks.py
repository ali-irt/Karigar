# emechanics/urls.py
from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import JobRequestViewSet, QuoteViewSet, MechanicProfileViewSet

router = DefaultRouter()
router.register(r'mechanics', MechanicProfileViewSet, basename='mechanic')
router.register(r'jobs', JobRequestViewSet, basename='job')
router.register(r'quotes', QuoteViewSet, basename='quote')

urlpatterns = [
    path('api/v1/', include(router.urls)),
]
