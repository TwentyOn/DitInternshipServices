from django.urls import path
from .views import GetAllowedServices

urlpatterns = [
    path('allowed_services/', GetAllowedServices.as_view()),
]