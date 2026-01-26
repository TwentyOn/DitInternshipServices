from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils import timezone


class Product(models.Model):
    name = models.TextField(unique=True, db_comment='Название продукта')
    ym_counter = models.TextField(db_comment='Номер счетчика яндекс метрики')
    yd_login = models.TextField(db_comment='Логин агентского кабинета Директа (текущий)')
    links = ArrayField(models.CharField(max_length=75), db_comment='Ссылки на продукт')  # This field type is a guess.
    user_id = models.IntegerField(db_comment='связь с юзером из БД dit-services')
    created_at = models.DateTimeField(db_comment='Дата-время создания', default=timezone.now)
    updated_at = models.DateTimeField(blank=True, null=True, db_comment='Дата-время последнего обновления',
                                      auto_now=True)
    to_delete = models.BooleanField(db_comment='Флаг используемый для "мягкого" удаления продукта',
                                    default=False)

    class Meta:
        managed = False
        db_table = 'campaign_stats"."product'
        db_table_comment = 'Таблица продуктов'


class GlobalCampaign(models.Model):
    product = models.ForeignKey('Product', models.DO_NOTHING, db_comment='Идентификатор продукта')
    yd_login = models.TextField(db_comment='Логин агентского кабинета Директа')
    name = models.TextField(unique=True, db_comment='Название кампании')
    started_at = models.DateTimeField(db_comment='Дата-время начала кампании')
    ended_at = models.DateTimeField(db_comment='Дата-время окончания кампании')
    user_id = models.IntegerField(db_comment='связь с юзером из БД dit-services')
    created_at = models.DateTimeField(db_comment='Дата-время создания', default=timezone.now)
    updated_at = models.DateTimeField(blank=True, null=True, db_comment='Дата-время последнего обновления',
                                      auto_now=True)
    to_delete = models.BooleanField(db_comment='Флаг, используемый для "мягкого" удаления глобальной кампании',
                                    default=False)

    class Meta:
        managed = False
        db_table = 'campaign_stats"."global_campaign'
        db_table_comment = 'глобальные кампании'


class GroupSets(models.Model):
    id = models.BigAutoField(primary_key=True, db_comment='Идентификатор')
    global_campaign = models.ForeignKey(GlobalCampaign, models.DO_NOTHING, db_comment='Айди глобальной кампании')
    group_set_serial_number = models.IntegerField(db_comment='Порядковый номер набора групп')
    name = models.TextField(db_comment='Название набора групп')

    class Meta:
        managed = False
        db_table = 'campaign_stats"."group_sets'
        db_table_comment = 'Наборы групп внутри глобальной кампании'


class CampaignGroup(models.Model):
    name = models.TextField(db_comment='Название группы')
    group_set = models.ForeignKey('GroupSets', models.DO_NOTHING,
                                  db_comment='Айди набора групп внутри кампаний которой принадлежит группа')
    group_serial_number = models.IntegerField(db_comment='Порядковый номер группы внутри набора групп')

    class Meta:
        managed = False
        db_table = 'campaign_stats"."campaign_group'
        db_table_comment = 'Группы кампаний'


class SpecificationPurpose(models.Model):
    product = models.ForeignKey(Product, models.DO_NOTHING, db_comment='Идентификатор продукта')
    user_id = models.IntegerField(db_comment='Связь с юзером из БД dit-services')
    created_at = models.DateTimeField(db_comment='Дата-время создания', default=timezone.now)
    updated_at = models.DateTimeField(blank=True, null=True, db_comment='Дата-время последнего обновления',
                                      auto_now=True)
    name = models.TextField(db_comment='Название справочника')
    number = models.IntegerField(blank=True, null=True, db_comment='Количество целей в справочнике')
    to_delete = models.BooleanField(db_comment='Флаг, используемый для "мягкого" удаления справочника целей',
                                    default=False)

    class Meta:
        managed = False
        db_table = 'campaign_stats"."specification_purpose'
        db_table_comment = 'справочник целей'


class Purpose(models.Model):
    id = models.BigAutoField(primary_key=True, db_comment='Идентификатор')
    purpose_specification = models.ForeignKey(SpecificationPurpose, models.DO_NOTHING,
                                              db_comment='Айди справочника целей к которому принадлежит цель')
    group_serial_number = models.IntegerField(db_comment='Порядковый номер группы целей в справочнике')
    purpose_serial_number = models.IntegerField(db_comment='Порядковый номер цели внутри группы')
    purpose_id = models.TextField(db_comment='Айди цели (в яндекс метрике)')
    ym_name = models.TextField(db_comment='Название цели в яндекс метрике')
    final_name = models.TextField(db_comment='Финальное название цели (самостоятельно исправленное)')
    group_name = models.TextField(db_comment='Имя группы целей')

    class Meta:
        managed = True
        db_table = 'campaign_stats"."purpose'
        db_table_comment = 'Таблица целей'


class Status(models.Model):
    id = models.IntegerField(primary_key=True, db_comment='Уникальный идентификатор')
    name = models.TextField(db_comment='Название статуса')
    description = models.TextField(blank=True, null=True, db_comment='Расширенное описание статуса')

    class Meta:
        managed = False
        db_table = 'campaign_stats"."status'
        db_table_comment = 'справочник статусов'


class Report(models.Model):
    id = models.BigAutoField(primary_key=True, db_comment='Уникальный идентификатор')
    user_id = models.IntegerField(db_comment='Связь с юзером из БД dit-services')
    created_datetime = models.DateTimeField(db_comment='Время создание заявки', auto_now_add=True)
    status = models.ForeignKey(Status, models.DO_NOTHING, db_comment='Айди статуса заявки')
    product = models.ForeignKey(Product, models.DO_NOTHING, db_comment='Айди продукта')
    global_campaign = models.ForeignKey(GlobalCampaign, models.DO_NOTHING, db_comment='Айди глобальной кампании')
    specification_action = models.ForeignKey('SpecificationAction', models.DO_NOTHING,
                                             db_comment='Айди справочника действий')
    specification_purpose = models.ForeignKey('SpecificationPurpose', models.DO_NOTHING,
                                              db_comment='Айди справочника целей')
    from_datetime = models.DateTimeField(db_comment='Дата-время начала периода')
    to_datetime = models.DateTimeField(db_comment='Дата-время окончания периода')
    filepath = models.TextField(blank=True, null=True, db_comment='Путь/ссылка к файлу отчёта')
    previous_filepath = models.TextField(blank=True, null=True, db_comment='Путь/ссылка к файлу предыдущего отчёта')
    to_delete = models.BooleanField(blank=True, db_comment='Флаг об удалении, выставляемый пользователем',
                                    default=False)

    class Meta:
        managed = False
        db_table = 'campaign_stats"."report'
        db_table_comment = 'Таблица отчётов'


class SheetsForForming(models.Model):
    report = models.ForeignKey(Report, models.DO_NOTHING, db_comment='Айди отчёта')
    organic = models.BooleanField(db_comment='Органический трафик')
    separate_yd_campaigns = models.BooleanField(db_comment='Отдельно по каждой кампании в директе')
    manually_created_groups = models.BooleanField(db_comment='Группы, сформированные вручную')
    visited_pages = models.BooleanField(db_comment='Посещенные страницы')
    age = models.BooleanField(db_comment='Возраст аудитории')
    gender = models.BooleanField(db_comment='Пол аудитории')
    long_term_interests = models.BooleanField(db_comment='Долгосрочные интересы аудитории')
    geography = models.BooleanField(db_comment='География аудитории')
    devices = models.BooleanField(db_comment='Устройства аудитории')

    class Meta:
        managed = False
        db_table = 'campaign_stats"."sheets_for_forming'
        db_table_comment = 'Таблица листов формирования для каждого отчёта'


class SpecificationAction(models.Model):
    name = models.TextField(unique=True, db_comment='Название справочника')
    product = models.ForeignKey(Product, models.DO_NOTHING, db_comment='Идентификатор продукта')
    user_id = models.IntegerField(db_comment='Связь с юзером из БД dit-services')
    number = models.IntegerField(db_comment='Количество действий в справочнике')
    created_at = models.DateTimeField(db_comment='Дата-время создания', default=timezone.now)
    updated_at = models.DateTimeField(blank=True, null=True, db_comment='Дата-время последнего обновления',
                                      auto_now=True)
    to_delete = models.BooleanField(db_comment='Флаг, используемый для "мягкого" удаления справочника действий',
                                    default=False)

    class Meta:
        managed = False
        db_table = 'campaign_stats"."specification_action'
        db_table_comment = 'справочник действий'


class Action(models.Model):
    id = models.BigAutoField(primary_key=True, db_comment='Идентификатор')
    specification_action = models.ForeignKey(SpecificationAction, models.DO_NOTHING,
                                             db_comment='Айди справочника дейсвтий к которому действие принадлежит')
    group_serial_number = models.IntegerField(db_comment='Порядковый номер группы действий')
    group_name = models.TextField(db_comment='Имя набора групп')
    action_serial_number = models.IntegerField(db_comment='Порядковый номер действия внутри группы')
    name = models.TextField(db_comment='Название действия')
    params1 = models.TextField(blank=True, null=True, db_comment='Значение параметра 1')
    params2 = models.TextField(blank=True, null=True, db_comment='Значение параметра 2')
    params3 = models.TextField(blank=True, null=True, db_comment='Значение параметра 3')
    params4 = models.TextField(blank=True, null=True, db_comment='Значение параметра 4')
    params5 = models.TextField(blank=True, null=True, db_comment='Значение параметра 5')
    params6 = models.TextField(blank=True, null=True, db_comment='Значение параметра 6')
    params7 = models.TextField(blank=True, null=True, db_comment='Значение параметра 7')
    params8 = models.TextField(blank=True, null=True, db_comment='Значение параметра 8')
    params9 = models.TextField(blank=True, null=True, db_comment='Значение параметра 9')
    params10 = models.TextField(blank=True, null=True, db_comment='Значение параметра 10')

    class Meta:
        managed = False
        db_table = 'campaign_stats"."action'
        db_table_comment = 'Таблица действий, с указанием групп и справочников к которым они относятся'


class YdCampaign(models.Model):
    yd_campaign_serial_number = models.IntegerField(db_comment='Порядковый номер кампании яндекс директа в группу',
                                                    default=1)
    name = models.TextField(db_comment='Название кампании в директе')
    yd_campaign_id = models.TextField(db_comment='Айди кампании в директе')
    campaign_group = models.ForeignKey(CampaignGroup, models.DO_NOTHING, blank=True, null=True,
                                       db_comment='Айди группы кампаний, к которой относится кампания яндекс директа')

    class Meta:
        managed = False
        db_table = 'campaign_stats"."yd_campaign'
        db_table_comment = 'Таблица кампаний Яндекс Директа с разделением на группы внутри набора групп'
