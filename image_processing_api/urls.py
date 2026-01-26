from django.urls import path
from .views import NewRequest

urlpatterns = [
    path('', NewRequest.as_view()),
]
