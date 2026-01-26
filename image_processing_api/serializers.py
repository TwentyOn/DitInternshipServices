import os

from rest_framework import serializers
from django.core.validators import FileExtensionValidator
from dotenv import load_dotenv

ALLOWED_EXTENSIONS = ['png', 'webp', 'jpg', 'jpeg', 'svg', 'ai', 'eps', 'zip']


class Request(serializers.Serializer):
    file = serializers.FileField(
        validators=[FileExtensionValidator(ALLOWED_EXTENSIONS)],
        error_messages={'invalid': 'Неверный формат файла'}
    )
    format = serializers.CharField()
    quality = serializers.CharField()
    resolution = serializers.BooleanField()
    proportion = serializers.BooleanField()
    toggle_switch = serializers.BooleanField()
    height = serializers.IntegerField()
    width = serializers.IntegerField()
    vector = serializers.BooleanField()
