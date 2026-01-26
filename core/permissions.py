from rest_framework import permissions
from authorize.models import Service


class IsUpkPermission(permissions.BasePermission):
    """
    Определяет право доступа только пользователей группы УПК
    """

    def has_permission(self, request, view):
        return request.user.groups.filter(name='УПК').exists()

    def has_object_permission(self, request, view, obj):
        return True


class IsNotUpkPermission(permissions.BasePermission):
    """
    Определяет право доступа только пользователей группы Сторонний отдел
    """

    def has_permission(self, request, view):
        return request.user.groups.filter(name='Сторонний отдел')

    def has_object_permission(self, request, view, obj):
        return True


class AppPermission(permissions.BasePermission):
    """
    Определяет право доступа для приложения (сервиса)
    """

    def has_permission(self, request, view):
        django_app_name = view.__module__.split('.')[0]

        user_groups = [group_obj.name for group_obj in request.user.groups.all()]
        service = Service.objects.get(django_app_name=django_app_name)
        access = service.allowed_groups.filter(name__in=user_groups).exists()

        return access

    def has_object_permission(self, request, view, obj):
        return True
