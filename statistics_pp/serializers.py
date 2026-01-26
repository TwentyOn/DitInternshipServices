from rest_framework import serializers
from django.contrib.postgres.fields import ArrayField


class ProviderParameters(serializers.Serializer):
    okpd2 = serializers.ListField(child=serializers.IntegerField(), default=list)
    metrics = serializers.ListField(child=serializers.IntegerField(), default=list)
    regions = serializers.ListField(child=serializers.IntegerField(), default=list)
    segment = serializers.CharField(required=False, max_length=50, allow_null=True)


class NewSegment(serializers.Serializer):
    segment_name = serializers.CharField(max_length=200)
    okpd2_array = serializers.ListField(child=serializers.IntegerField())

class GetProcess(serializers.Serializer):
    request_id = serializers.IntegerField()

class GetChields(serializers.Serializer):
    parent_id = serializers.IntegerField()