from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import *

router = DefaultRouter()


urlpatterns = [
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
    path('register/client/', client_register, name='client_register'),    path('privacy-policy/', privacy_policy, name='privacy_policy'),
    path('terms-and-conditions/', terms_and_conditions, name='terms_and_conditions'),
    path('logout/', logout_view, name='logout'),
        path('mechanic/dashboard/', mechanic_dashboard, name='mechanic_dashboard'),

    path('api/v1/', include(router.urls)),
]
