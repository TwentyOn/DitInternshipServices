from rest_framework import serializers


class NewReport(serializers.Serializer):
    product_id = serializers.IntegerField()
    campaign_id = serializers.IntegerField()
    period_start = serializers.DateField(
        error_messages={
            'invalid': 'Дата начала периода имеет неправильный формат. Используйте один из следующих форматов: ГГГГ-ММ-ДД.'}
    )
    period_end = serializers.DateField(
        error_messages={
            'invalid': 'Дата окончания периода имеет неправильный формат. Используйте один из следующих форматов: ГГГГ-ММ-ДД.'}
    )
    action_handbook_id = serializers.IntegerField(allow_null=True)
    goal_handbook_id = serializers.IntegerField(allow_null=True)
    prev_campaign_sheet = serializers.CharField(allow_null=True)
    sheets_for_forming = serializers.DictField(child=serializers.BooleanField(), allow_null=True)


class NewProduct(serializers.Serializer):
    product_id = serializers.IntegerField(allow_null=True)
    product_name = serializers.CharField(max_length=50)
    counter_id = serializers.IntegerField(
        error_messages={
            'required': 'Введите № счётчика Яндекс Метрики',
            'invalid': 'Некорректый номер счётчика Я.Метрики. Допустимы только цифровые символы.'
        })
    direct_login = serializers.CharField(max_length=50, error_messages={'required': 'Введите логин Яндекс Директа'})
    product_urls = serializers.ListField(child=serializers.CharField(max_length=100))


class NewCampaignYdCampaign(serializers.Serializer):
    campaign_id = serializers.IntegerField(allow_null=True)
    yd_campaign_serial_number = serializers.IntegerField()
    yd_campaign_id = serializers.IntegerField()
    campaign_name = serializers.CharField(max_length=100)


class NewCampaignGroup(serializers.Serializer):
    group_id = serializers.IntegerField(allow_null=True)
    group_serial_number = serializers.IntegerField()
    name = serializers.CharField(max_length=75)
    campaigns = serializers.ListField(child=NewCampaignYdCampaign(), allow_empty=False, error_messages={
        'empty': 'В группе кампаний должна быть как минимум 1 кампания'
    })


class NewCampaignGroupSet(serializers.Serializer):
    group_set_id = serializers.IntegerField(allow_null=True)
    group_set_serial_number = serializers.IntegerField()
    name = serializers.CharField(max_length=75)
    groups = serializers.ListField(child=NewCampaignGroup(), allow_empty=False, error_messages={
        'empty': 'В наборе групп должна быть как минимум 1 группа.'
    })


class NewCampaign(serializers.Serializer):
    campaign_id = serializers.IntegerField(allow_null=True)
    campaign_name = serializers.CharField(max_length=75, error_messages={'blank': 'Имя кампании не может быть пустым'})
    product_id = serializers.IntegerField()
    period_start = serializers.DateField(error_messages={
        'invalid': 'Дата начала периода имеет неправильный формат. Используйте один из следующих форматов: ГГГГ-ММ-ДД.'})
    period_end = serializers.DateField(error_messages={
        'invalid': 'Дата окончания периода имеет неправильный формат. Используйте один из следующих форматов: ГГГГ-ММ-ДД.'})
    group_sets = serializers.ListField(child=NewCampaignGroupSet())


class NewActionHandbookAction(serializers.Serializer):
    action_serial_number = serializers.IntegerField()
    name = serializers.CharField(max_length=75)
    parameters = serializers.DictField(child=serializers.CharField(max_length=50, allow_null=True))

    def validate_parameters(self, value):
        """
        Метод для валидации поля parameters
        """
        if not any(v is not None for v in value.values()):
            raise serializers.ValidationError('Хотя бы один параметр в parameters должен быть не равен null')
        return value


class NewActionHandbookActionGroup(serializers.Serializer):
    action_group_serial_number = serializers.IntegerField()
    action_group_name = serializers.CharField(max_length=100)
    actions = serializers.ListField(child=NewActionHandbookAction(), allow_empty=False, error_messages={
        'empty': 'Группа действий должна содержать как минимум 1 действие'
    })


class NewActionHandbook(serializers.Serializer):
    action_handbook_id = serializers.IntegerField(allow_null=True)
    action_handbook_name = serializers.CharField(max_length=75)
    product_id = serializers.IntegerField()
    actions_count = serializers.IntegerField(
        error_messages={'required': 'Ошибка создания - не был получен параметр общего кол-ва действий.'})
    action_groups = serializers.ListField(child=NewActionHandbookActionGroup(), allow_empty=False, error_messages={
        'empty': 'Справочник действий должен содержать как минимум 1 группу действий'
    })


class NewGoalHandbookGoal(serializers.Serializer):
    purpose_serial_number = serializers.IntegerField()
    purpose_id = serializers.CharField(max_length=50)
    final_name = serializers.CharField(max_length=75)
    ym_name = serializers.CharField(max_length=100)


class NewGoalHandbookGoalGroup(serializers.Serializer):
    purpose_group_serial_number = serializers.IntegerField()
    purpose_group_name = serializers.CharField(max_length=100)
    purposes = serializers.ListField(child=NewGoalHandbookGoal(), allow_empty=False, error_messages={
        'empty': 'Группа целей должна содержать как минимум 1 цель'
    })


class NewGoalHandbook(serializers.Serializer):
    goal_handbook_id = serializers.IntegerField(allow_null=True)
    goal_handbook_name = serializers.CharField(max_length=75)
    product_id = serializers.IntegerField()
    purpose_count = serializers.IntegerField()
    purpose_groups = serializers.ListField(child=NewGoalHandbookGoalGroup(), allow_empty=False, error_messages={
        'empty': 'Справочник целей должен содержать как минимум 1 группу целей'
    })
