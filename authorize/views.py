from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth.models import User, Group

from core.permissions import IsUpkPermission
from .models import Service


# Create your views here.
class GetAllowedServices(APIView):
    def get(self, request):
        user: User = request.user
        user_groups = user.groups.all()
        allowed_services = Service.objects.filter(allowed_groups__in=user_groups)
        return Response(
            {
                'user_id': user.pk,
                'allowed_services': [{
                    'id': service_obj.pk,
                    'name': service_obj.name
                } for service_obj in allowed_services]
            }
        )
