from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from .views import * 

# --- 1. Traditional Django Paths ---
# Assuming these views (index, about, login_view, etc.) are simple function-based or TemplateViews
traditional_patterns = [
    path('', index, name='index'),
    path('about/', about, name='about'),
    path('services/', services, name='services'),
    path('how-it-work/', how_it_work, name='how_it_work'),
    path('safety/', safety, name='safety'),
    path('faq/', faq, name='faq'),
    path('career/', career, name='career'),
    path('contact/', contact, name='contact'),
    path('search/', search, name='search'),
    path('login/', login_view, name='login_view'),
    path('register/mechanic/', mechanic_register, name='mechanic_register'),
    path('register/client/', client_register, name='client_register'),
    path('privacy-policy/', privacy_policy, name='privacy_policy'),
    path('terms-and-conditions/', terms_and_conditions, name='terms_and_conditions'),
    path('logout/', logout_view, name='logout'),
    path('webhooks/<uuid:webhook_uuid>/', uuid_webhook_receiver, name='uuid_webhook_receiver'),
    path('mechanic/dashboard/', mechanic_dashboard, name='mechanic_dashboard'),
   ]

# --- 2. Django REST Framework API Paths ---

# Create a default router for top-level viewsets
router = DefaultRouter()

# --- Auth and User ---
router.register(r'auth', AuthViewSet, basename='auth')
router.register(r'users', UserProfileViewSet, basename='user')

# --- Customer Flow ---
router.register(r'vehicles', VehicleViewSet, basename='vehicle')
router.register(r'mechanics', MechanicViewSet, basename='mechanic')
router.register(r'service-types', ServiceTypeViewSet, basename='service-type')
router.register(r'promotions', PromotionViewSet, basename='promotion')
router.register(r'wallets', WalletViewSet, basename='wallet')

# --- Mechanic Flow ---
router.register(r'mechanic-profiles', MechanicProfileViewSet, basename='mechanic-profile')
router.register(r'mechanic-documents', MechanicDocumentViewSet, basename='mechanic-document')
router.register(r'mechanic-services', MechanicServiceViewSet, basename='mechanic-service')

# --- Core Service Flow ---
router.register(r'service-requests', ServiceRequestViewSet, basename='service-request')


# --- Nested Routes for ServiceRequestItem (Service Completion Flow) ---
# This requires the 'rest_framework_nested' package.
# 1. Create a simple router for the parent resource (ServiceRequest)
service_requests_router = routers.SimpleRouter()
service_requests_router.register(r'service-requests', ServiceRequestViewSet, basename='service-request')

# 2. Create a nested router for the child resource (ServiceRequestItem)
# The lookup argument 'service_request' matches the service_request_pk used in the ViewSet
items_router = routers.NestedSimpleRouter(service_requests_router, r'service-requests', lookup='service_request')
items_router.register(r'items', ServiceRequestItemViewSet, basename='service-request-item')


# --- Final URL Pattern List ---
urlpatterns = traditional_patterns + [
    # API endpoints are nested under 'api/v1/' as requested
    path('api/', include(router.urls)),
    # Nested routes must be included separately
    path('api/', include(items_router.urls)),
]
