from django.db import models

from django.contrib.auth.models import Group


# Create your models here.
class Service(models.Model):
    name = models.CharField()
    django_app_name = models.CharField()
    allowed_groups = models.ManyToManyField(Group, db_table='authorize_service_group')

    class Meta:
        db_table = 'service'
        managed = False

    def __str__(self):
        return self.name
