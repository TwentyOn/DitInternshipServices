from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password


class CreateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'password']
        extra_kwargs = {'password': {'write_only': True}}

    def validate_password(self, password: str):
        validate_password(password)
        return password

    def create(self, validated_data):
        # new_user = User(email=validated_data.get('email'))
        # new_user.set_password(validated_data.get('password'))
        # new_user.save()
        new_user = User.objects.create_user(**validated_data, username='aboba')
        return new_user
