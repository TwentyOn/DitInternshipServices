from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone


# Create your models here.


class Segment(models.Model):
    name = models.CharField(max_length=255, unique=True, db_comment='Имя сегмента')

    class Meta:
        db_table = 'schema_pp_internal"."segments'
        db_table_comment = (
            'Таблица для хранения имён пользовательских сегментов, связана отношением ManyToMany c таблицей OKPD2')


class OKPD2(models.Model):
    code = models.IntegerField(db_comment='ссылка на запись таблицы okpd2_codifier')
    description = models.TextField(db_comment='Имя (описание) ОКПД2-кода кодовое')
    segments = models.ManyToManyField(Segment)

    class Meta:
        db_table = 'schema_pp_internal"."okpd2'
        db_table_comment = (
            'Таблица для ОКПД2 кодов, cвязана отношением ManyToMany с таблицей Segment')


class OKPD2Codifier(models.Model):
    code = models.TextField(null=False, db_comment='ОКПД2-код c портала поставщиков')
    description = models.TextField(null=False, db_comment='Имя (описание) ОКПД2-кода текстовое')
    parent_id = models.IntegerField(null=False,
                                    db_comment='Идентификатор родительского ОКПД2-кода, если == 0 значит данный код не имеет родителей')
    active = models.BooleanField(null=True)

    class Meta:
        db_table = 'schema_pp_official"."okpd2_codifier'
        db_table_comment = 'Таблица для хранения ОКПД2-кодов с описанием и метками (parent_id) на родительские ОКПД2-коды'


class Region(models.Model):
    region_code = models.CharField(max_length=50, null=False, db_comment='Код региона с ПП')
    region_name = models.CharField(max_length=255, null=False, db_comment='Название региона')

    class Meta:
        db_table = 'schema_pp_internal"."regions'
        db_table_comment = 'Таблица для хранения кодов и названий регионов с ПП, связана отношением OneToMany с таблицей RegionCodifier'


class RegionCodifier(models.Model):
    region_code = models.CharField(max_length=50, db_comment='Код региона')
    region_name = models.CharField(max_length=255, db_comment='Имя региона')
    region = models.ForeignKey(Region, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = 'schema_pp_official"."regions_codifier'
        db_table_comment = 'Таблица для хранения названий регионов, связана отношением OneToMany с таблицей Region'


class Metric(models.Model):
    name = models.CharField(max_length=255, unique=True,
                            db_comment='Уникальное имя метрики (параметра) в соответствии с которым собирается статистика')

    class Meta:
        db_table = 'schema_pp_internal"."metrics'
        db_table_comment = 'Таблица для хранения метрик на сбор статистики ПП'


class Process(models.Model):
    okpd2_ids = ArrayField(base_field=models.IntegerField(), db_comment='массив идентификаторов ОКПД2')
    region_ids = ArrayField(base_field=models.IntegerField(), db_comment='массив идентификаторов регионов')
    metrics = ArrayField(base_field=models.IntegerField(), db_comment='массив метрик (параметров) сбора статистики')
    completed = models.IntegerField(default=-1,
                                    db_comment='поле готовности процесса: -1 не принято в обработку; 0 обрабатывается; 1 обработано')
    progress = models.IntegerField(default=0, db_comment='прогресс обработки процесса, процент')
    data_file = models.URLField(default=None, null=True, db_comment='адрес файла в S3 хранилище')
    error_msg = models.TextField(null=True, db_comment='поле для хранения сообщений об ошибках сбора статистики')
    updated_at = models.DateTimeField(auto_now=True, null=True,
                                      db_comment='информация о дате-времени последнего обновления поля')

    class Meta:
        db_table = 'schema_pp_internal"."processes'
        db_table_comment = (
            'Таблица процесса (задания) на сбор статистики ПП в соответствии с переданными параметрами (okpd2_ids, region_ids, metrics) используется для добавления заданий на сбор статистики и выдачу результатов')


class IntermediateData(models.Model):
    process = models.ForeignKey(Process, null=False, on_delete=models.CASCADE)
    okpd2 = models.ForeignKey(OKPD2Codifier, null=False, on_delete=models.CASCADE)
    contracts_count = models.IntegerField(null=True)
    offers_total = models.IntegerField(null=True)
    offers_active = models.IntegerField(null=True)
    completed = ArrayField(base_field=models.IntegerField())

    class Meta:
        db_table = 'schema_pp_internal"."intermediate_data'
        db_table_comment = 'Таблица мини-задач'
