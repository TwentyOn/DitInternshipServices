import json
import os.path
import sys

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import APIException

from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.db.models import ObjectDoesNotExist
from django.db import transaction
from django.shortcuts import get_object_or_404, Http404

import requests

from .models import Product, GlobalCampaign, Report, SpecificationAction, SpecificationPurpose, Status, \
    SheetsForForming, YdCampaign, Action, Purpose, GroupSets, CampaignGroup
from .serializers import NewReport, NewProduct, NewCampaign, NewActionHandbook, NewGoalHandbook

from core.settings import YM_AUTH_TOKEN, YD_AUTH_TOKEN, BASE_DIR, ACCESS_KEY, BUCKET_NAME
from core.minio_storage import storage


def error_formatter(serializer_errors):
    """
    Функция для форматирования словаря ошибок сериализатора django в формат для отображения на фронтенде
    ВНИМАНИЕ -  не корректно работает для поля типа DictField
    """
    # получаем список со списками ошибок по каждому полю сериализатора
    error_lists = serializer_errors.values()
    # извлекаем и объединяем в единую строку ошибки по каждому полю
    errors_sep = [', '.join(error_list) if type(error_list) is list else error_formatter(error_list) for error_list in
                  error_lists]
    # объединяем ошибки по всем полям сериализатора в единую строку
    errors_sep = ' --- '.join(set(errors_sep))

    return errors_sep


class FormatterMixin:
    """
    Миксин для форматирования данных различных объектов из БД в схемы для HTTP-ответов
    """

    def report_form(self, report_obj):
        return {
            'report_id': report_obj.pk,
            'product_id': report_obj.product_id,
            'products_name': report_obj.product.name,
            'campaign_name': report_obj.global_campaign.name,
            'created': report_obj.created_datetime.date(),
            'period_start': report_obj.from_datetime.date(),
            'period_end': report_obj.to_datetime.date(),
            'status': report_obj.status.id,
            'file_url': storage.share_file_from_bucket(report_obj.filepath) if report_obj.filepath else None
        }

    def previous_report_form(self, report_obj):
        return {
            'name': report_obj.filepath.split('/')[-1].replace('.xlsx', ''),
            'path': report_obj.filepath
        }

    def product_form(self, product_obj):
        return {
            'product_id': product_obj.pk,
            'product_name': product_obj.name,
            'YM_counter': product_obj.ym_counter,
            'YD_login': product_obj.yd_login,
            'product_urls': product_obj.links
        }

    def campaign_form(self, campaign_obj):
        return {
            'campaign_id': campaign_obj.pk,
            'campaign_name': campaign_obj.name,
            'period_start': campaign_obj.started_at.date(),
            'period_end': campaign_obj.ended_at.date()
        }

    def action_handbook_form(self, action_handbook_obj):
        return {
            'action_handbook_id': action_handbook_obj.pk,
            'action_handbook_name': action_handbook_obj.name
        }

    def goal_handbook_form(self, goal_handbook_obj):
        return {
            'goal_handbook_id': goal_handbook_obj.pk,
            'goal_handbook_name': goal_handbook_obj.name
        }


# Create your views here.
class Reports(APIView, FormatterMixin):
    def get(self, request):
        """
        Возврат данных для отображения карточек существующих отчётов
        """
        try:
            result = {'reports': map(self.report_form, Report.objects.filter(to_delete=False))}
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения отчётов: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @transaction.atomic
    def post(self, request):
        """
        Создание нового или обновление уже созданного отчёта
        """
        serializer = NewReport(data=request.data)
        if serializer.is_valid():
            try:
                new_report = Report.objects.create(
                    status=Status.objects.get(pk=0),
                    product=get_object_or_404(Product, pk=serializer.data['product_id']),
                    global_campaign=get_object_or_404(GlobalCampaign, pk=serializer.data['campaign_id']),
                    from_datetime=serializer.data['period_start'],
                    to_datetime=serializer.data['period_end'],
                    specification_action_id=serializer.data['action_handbook_id'],
                    specification_purpose_id=serializer.data['goal_handbook_id'],
                    previous_filepath=serializer.data.get('prev_campaign_sheet'),
                    user_id=request.user.id
                )
                # добавление параметров формирования отчёта в подчинённую таблицу
                new_report.sheetsforforming_set.add(
                    SheetsForForming(**serializer.data['sheets_for_forming']),
                    bulk=False
                )
                return Response({'message': 'Отчёт успешно добавлен в очередь на формирование'})

            # обработка исключения связанного с попыткой создания отчёта с привязкой к несуществующему объекту
            except ObjectDoesNotExist as err:
                return Response({'message': str(err)}, status=status.HTTP_404_NOT_FOUND)

            except Exception as err:
                return Response({'message': str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # если произошла ошибка валидации параметров сериализатора
        else:
            print(serializer.errors)
            return Response({'message': error_formatter(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)


class ReportToEdit(APIView):
    def delete(self, request, report_id):
        """
        'Мягкое' удаление существующих отчётов
        """
        try:
            report = get_object_or_404(Report, pk=report_id, to_delete=False)
            report.to_delete = True
            report.save()
            return Response({'message': 'Отчёт успешно удалён'})
        except Exception as err:
            return Response({'message': f'Ошибка удаления отчёта: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateReportData(APIView, FormatterMixin):
    def get(self, request):
        """
        Возвращает сопутствующие данные, требуемые для создания нового отчёта
        """
        try:
            products = Product.objects.filter(to_delete=False)

            # индивидуальная схема ответа для страницы создания отчёта
            product_formatter = lambda product_obj: {
                "product_id": product_obj.pk,
                "products_name": product_obj.name,
                "actions_handbooks": [
                    self.action_handbook_form(obj) for obj in
                    product_obj.specificationaction_set.filter(to_delete=False)
                ],
                "goals_handbooks": [
                    self.goal_handbook_form(obj) for obj in product_obj.specificationpurpose_set.filter(to_delete=False)
                ],
                "campaigns": [
                    self.campaign_form(obj) for obj in product_obj.globalcampaign_set.filter(to_delete=False)
                ],
                "previous_reports": [
                    self.previous_report_form(report_obj) for report_obj in
                    product_obj.report_set.filter(to_delete=False, status_id=2, filepath__isnull=False)
                ]
            }

            result = [product_formatter(obj) for obj in products]
            return Response(dict(products=result))
        except Exception as err:
            return Response({'message': f'Ошибка получения данных для создания отчёта: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class Products(APIView, FormatterMixin):
    def product_form(self, product_obj):
        result = super().product_form(product_obj)
        del result['product_urls']
        result['created'] = product_obj.created_at.date()
        return result

    def get(self, request):
        """
        Возвращает данные для отображения карточек существующих продуктов
        """
        try:
            all_products = Product.objects.only('pk', 'name', 'ym_counter', 'yd_login', 'created_at').filter(
                to_delete=False)
            result = {'products': map(self.product_form, all_products)}
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения продуктов: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request):
        """
        Создание нового или обновление существующего продукта
        """
        serializer = NewProduct(data=request.data)
        if serializer.is_valid():
            exist_product_id, name, ym_counter, yd_login, links = serializer.data.values()
            if exist_product_id:
                operation = 'обновлён.'
                new_product = get_object_or_404(Product, pk=exist_product_id, to_delete=False)
            else:
                operation = 'создан.'
                new_product = Product()
                new_product.user_id = request.user.id

            new_product.name = name
            new_product.ym_counter = ym_counter
            new_product.yd_login = yd_login
            new_product.links = links

            try:
                # если имя продукта уже существует, возвращаем ошибку
                # при обновлении из выборки исключается обновляемый продукт, т.е его имя не учитывается
                if Product.objects.filter(name=name).exclude(pk=exist_product_id).exists():
                    return Response({'message': f"Имя продукта '{name}' уже используется."},
                                    status=status.HTTP_409_CONFLICT)

                new_product.save()
                return Response({'message': f'Продукт успешно {operation}'})

            except Exception as err:
                return Response({'message': str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({'message': error_formatter(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)


class ProductToEdit(APIView, FormatterMixin):
    def get(self, request, product_id):
        """
        Получение данных существующего, неудалённого продукта для редактирования
        """
        try:
            product = get_object_or_404(Product, pk=product_id, to_delete=False)
            result = self.product_form(product)
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения данных для редактирования продукта: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, product_id):
        """
        Удаление существующего продукта
        """
        try:
            product = get_object_or_404(Product, pk=product_id, to_delete=False)
            product.to_delete = True
            product.save()
            return Response({'message': 'Продукт успешно удалён'})
        except Exception as err:
            return Response({'message': f'Ошибка удаления продукта: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductsDropdownList(APIView):
    def get(self, request):
        """
        Получения пар значений product_id:product_name для выпадающих списков, используемых на странице создания
        новых сущностей
        """
        try:
            result = Product.objects.only('id', 'name').filter(to_delete=False)
            return Response({'products': [{'product_id': product_obj.pk,
                                           'product_name': product_obj.name} for product_obj in result]})
        except Exception as err:
            return Response({'message': f'Ошибка получения выпадающего списка продуктов: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class Campaigns(APIView, FormatterMixin):
    def campaign_form(self, campaign_obj):
        result = super().campaign_form(campaign_obj)
        result['product_id'] = campaign_obj.product_id
        result['product_name'] = campaign_obj.product.name
        result['created'] = campaign_obj.created_at.date()
        return result

    def get(self, request):
        """
        Получение данных для отображения карточек существующих глобальных кампаний
        """
        try:
            # объект-итератор с данными о глобальной кампании
            result = {'campaigns': map(self.campaign_form, GlobalCampaign.objects.filter(to_delete=False))}
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения глобальных кампаний: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @transaction.atomic
    def post(self, request):
        """
        Создание новой или редактирование существующей глобальной кампании, в т.ч сопутствующих данных в
        виде наборов групп, групп и кампаний кампаний Яндекс Директ, входящих в группу
        """
        serializer = NewCampaign(data=request.data)
        if serializer.is_valid():
            try:
                exist_campaign_id, campaign_name, product_id, period_start, period_end, group_sets = serializer.data.values()

                # обработка исключения с попыткой создания продукта, имя которого уже занято
                if GlobalCampaign.objects.filter(name=campaign_name).exclude(pk=exist_campaign_id).exists():
                    return Response({'message': f"Имя глобальной кампании '{campaign_name}' уже используется."},
                                    status=status.HTTP_409_CONFLICT)

                yd_login = Product.objects.get(pk=product_id, to_delete=False).yd_login

                # если редактируется существующая кампания
                if exist_campaign_id:
                    new_global_campaign = get_object_or_404(GlobalCampaign, pk=exist_campaign_id, to_delete=False)
                # если создаётся новая кампания
                else:
                    new_global_campaign = GlobalCampaign()
                    new_global_campaign.user_id = request.user.id

                new_global_campaign.product_id = product_id
                new_global_campaign.yd_login = yd_login
                new_global_campaign.name = campaign_name
                new_global_campaign.started_at = period_start
                new_global_campaign.ended_at = period_end
                new_global_campaign.save()

                # заполнение наборов групп для глобальной кампании
                if exist_campaign_id:
                    return self.create_or_update_campaign_group_items(group_sets, new_global_campaign, update=True)
                return self.create_or_update_campaign_group_items(group_sets, new_global_campaign)

            # обработка исключения при несуществующем заданном продукте кампании
            except ObjectDoesNotExist as err:
                return Response({'message': str(err)}, status=status.HTTP_404_NOT_FOUND)
            # перехватываем исключения APIException, вызываемое во вспомогательной функции create_or_update_campaign_group_items
            except APIException as err:
                raise err
            # перехват исключения Http404 вызываемое методом get_object_or_404
            except Http404 as err:
                raise err
            except Exception as err:
                return Response({'message': str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # обработка ошибки валидации входных параметров
        else:
            return Response(
                {'message': error_formatter(serializer.errors)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @staticmethod
    @transaction.atomic
    def create_or_update_campaign_group_items(group_sets, campaign_obj, update: bool = False):
        """
        Статический метод для создания / обновления наборов групп и сопутствующих данных глобальной кампании
        :param group_sets: набор групп полученный с фронтенда
        :param campaign_obj: вновь созданный или обновляемый объект модели GlobalCampaign
        :param update: флаг (bool) классифицирующий операцию (обновление или создание объекта)
        """
        # удаление лишних наборов групп
        # ID наборов групп которые пользователь обновляет
        input_group_set_ids = set([gr_set['group_set_id'] for gr_set in group_sets if gr_set['group_set_id']])
        # ID наборов групп из БД
        bd_group_sets_ids = set([set_obj.pk for set_obj in campaign_obj.groupsets_set.all()])
        # ID групп которые есть в БД но были удалены пользователем на стороне фронтенда (не пришли в запросе)
        not_return_group_sets_ids = bd_group_sets_ids.difference(input_group_set_ids)
        # ID наборов групп, которые не возвращены с клиента считаются удалёнными на фронтенде
        # и соответственно удаляются из базы данных
        if not_return_group_sets_ids:
            # удаление наборов групп с ID из not_return_group_sets_ids
            GroupSets.objects.filter(pk__in=not_return_group_sets_ids).delete()
            print('Удаленные наборы групп:', not_return_group_sets_ids)

        # функционал заполнения наборов групп, групп, и кампаний ЯД для объекта campaign_obj
        # парсинг наборов групп
        for group_set in group_sets:
            # если у campaign_obj уже существует набор групп с данным именем, возбуждается исключение
            if GroupSets.objects.filter(global_campaign=campaign_obj, name=group_set['name']).exclude(
                    pk=group_set['group_set_id']).exists():
                exc = APIException(
                    {
                        'message': f"Набор групп с наименованием '{group_set['name']}' уже существует для данной кампании."})
                exc.status_code = status.HTTP_409_CONFLICT
                raise exc

            # если набор групп редактируется, извлекаем существующий набор групп из БД
            if group_set['group_set_id']:
                new_group_set = get_object_or_404(GroupSets, pk=group_set['group_set_id'])

                # алгоритм удаления групп из БД для данного набора групп, которые были удалены пользователем со стороны фронтенда
                # ID групп, которые пользователь обновил
                input_group_ids = {group['group_id'] for group in group_set['groups'] if group['group_id']}
                # ID групп из БД
                bd_group_ids = {campaign_group_obj.pk for campaign_group_obj in new_group_set.campaigngroup_set.all()}
                # ID групп, удаленных пользователем (на основе разности множеств)
                not_return_groups_ids = bd_group_ids.difference(input_group_ids)
                # удаление групп с ID из not_return_groups_ids
                if not_return_groups_ids:
                    new_group_set.campaigngroup_set.filter(pk__in=not_return_groups_ids).delete()
                    print('Удаленные группы:', not_return_groups_ids)
            # если создаётся новый набор групп
            else:
                new_group_set = GroupSets()

            new_group_set.group_set_serial_number = group_set['group_set_serial_number']
            new_group_set.name = group_set['name']
            new_group_set.global_campaign = campaign_obj
            new_group_set.save()

            # парсинг групп из набора групп
            for group in group_set['groups']:
                # если у campaign_obj уже существует группа с данным именем возбуждается исключение
                if CampaignGroup.objects.filter(group_set=new_group_set, name=group['name']).exclude(
                        pk=group['group_id']).exists():
                    exc = APIException(detail={
                        'message': f"Группа с наименованием '{group['name']}' уже существует в наборе групп '{new_group_set.name}'."})
                    exc.status_code = status.HTTP_409_CONFLICT
                    raise exc

                if group['group_id']:
                    new_group = get_object_or_404(CampaignGroup, pk=group['group_id'])

                    # удаление избыточных кампаний ЯД (те что есть в БД, но не пришли в запросе после редактирования)
                    # получение множества ID кампаний ЯД отредактированных пользователей на фронтенде
                    input_yd_campaign_ids = {yd_campaign['campaign_id'] for yd_campaign in group['campaigns'] if
                                             yd_campaign['campaign_id']}
                    # получение множества ID кампаний ЯД из БД
                    bd_yd_campaign_ids = {yd_campaign_obj.pk for yd_campaign_obj in new_group.ydcampaign_set.all()}
                    # разность множеств - получаем ID кампаний ЯД которые есть в БД, но не вернулись с фронтенда
                    not_return_yd_campaigns_ids = bd_yd_campaign_ids.difference(input_yd_campaign_ids)
                    # удаление кампаний ЯД если они не вернулись с фронтента после редактирования (т.е были удалены)
                    if not_return_yd_campaigns_ids:
                        print('Удаленные кампании ЯД:', not_return_yd_campaigns_ids)
                        YdCampaign.objects.filter(pk__in=not_return_yd_campaigns_ids).delete()
                else:
                    new_group = CampaignGroup()

                new_group.group_serial_number = group['group_serial_number']
                new_group.name = group['name']
                new_group.group_set = new_group_set
                new_group.save()

                # парсинг кампаний ЯД из группы
                for yd_campaign in group['campaigns']:
                    if yd_campaign['campaign_id']:
                        new_yd_campaign = get_object_or_404(YdCampaign, pk=yd_campaign['campaign_id'])
                    else:
                        new_yd_campaign = YdCampaign()

                    new_yd_campaign.yd_campaign_serial_number = yd_campaign['yd_campaign_serial_number']
                    new_yd_campaign.name = yd_campaign['campaign_name']
                    new_yd_campaign.yd_campaign_id = yd_campaign['yd_campaign_id']
                    new_yd_campaign.campaign_group = new_group
                    new_yd_campaign.save()
        return Response({'message': f'Глобальная кампания успешно {"обновлена" if update else "создана"}.'})


class CampaignToEdit(APIView, FormatterMixin):
    def campaign_form(self, campaign_obj):
        result = super().campaign_form(campaign_obj)
        result['product_id'] = campaign_obj.product_id

        # получение ID ЯД кампаний, которые были закреплены за глобальной кампанией для отображения на фронтенде
        yd_campaigns_objects = (YdCampaign.objects.filter(campaign_group__group_set__global_campaign=campaign_obj))
        result['YD_campaigns_ids_active'] = [yd_campaign_obj.yd_campaign_id for yd_campaign_obj in yd_campaigns_objects]

        # запролнение наборов групп, групп и кампаний ЯД для данной глобальной кампании
        result['group_sets'] = [{
            'group_set_id': group_set_obj.pk,
            'group_set_serial_number': group_set_obj.group_set_serial_number,
            'name': group_set_obj.name,
            'groups': [{
                'group_id': group_obj.pk,
                'group_serial_number': group_obj.group_serial_number,
                'name': group_obj.name,
                'campaigns': [{
                    'campaign_id': yd_campaign_obj.pk,
                    'yd_campaign_serial_number': yd_campaign_obj.yd_campaign_serial_number,
                    'yd_campaign_id': yd_campaign_obj.yd_campaign_id,
                    'campaign_name': yd_campaign_obj.name
                } for yd_campaign_obj in group_obj.ydcampaign_set.all()]
            } for group_obj in group_set_obj.campaigngroup_set.all()]
        } for group_set_obj in campaign_obj.groupsets_set.all()]
        return result

    def get(self, request, campaign_id):
        """
        Получение данных существующей, неудаленной глобальной кампании для редактирования
        """
        campaign = get_object_or_404(GlobalCampaign, pk=campaign_id, to_delete=False)
        try:
            return Response(self.campaign_form(campaign))
        except Exception as err:
            return Response({'message': f'Ошибка получения данных для редактирования глобальной кампании: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, campaign_id):
        """
        Удаление существующей глобальной кампании
        """
        try:
            campaign = get_object_or_404(GlobalCampaign, pk=campaign_id, to_delete=False)
            campaign.to_delete = True
            campaign.save()
            return Response({'message': 'Глобальная кампания успешно удалена'})
        except Exception as err:
            return Response({'message': f'Ошибка удаления глобальной кампании: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ActionsHandbooks(APIView, FormatterMixin):
    def action_handbook_form(self, action_handbook_obj):
        result = super().action_handbook_form(action_handbook_obj)
        result.update({'product_id': action_handbook_obj.product_id,
                       'product_name': action_handbook_obj.product.name,
                       'created': action_handbook_obj.created_at.date(),
                       'actions_count': action_handbook_obj.number})
        return result

    def get(self, request):
        """
        Получение данных для отображения карточек справочников действий
        """
        try:
            result = map(self.action_handbook_form, SpecificationAction.objects.filter(to_delete=False))
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения справочников действий: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @transaction.atomic
    def post(self, request):
        """
        Создание нового или обновление существующего справочника действий
        """
        serializer = NewActionHandbook(data=request.data)
        if serializer.is_valid():
            exist_handbook_id, name, product_id, actions_count, action_groups = serializer.data.values()

            # проверка, не занято ли заданное пользователем имя для справочника действий для заданного продукта
            if SpecificationAction.objects.filter(name=name, product_id=product_id).exclude(
                    pk=exist_handbook_id).exists():
                return Response(
                    dict(message='Заданное имя справочника действий уже используется для данного продукта.'),
                    status=status.HTTP_409_CONFLICT)

            # если обновляется существующий объект
            if exist_handbook_id:
                new_action_handbook = get_object_or_404(SpecificationAction, pk=exist_handbook_id, to_delete=False)
                # множество для отслеживания ID созданных или отредактированых наборов действий / действий
                edited_or_created_objects_ids = set()
            # если создаётся новый объект
            else:
                new_action_handbook = SpecificationAction()
                new_action_handbook.user_id = request.user.id

            new_action_handbook.name = name
            new_action_handbook.product_id = product_id
            new_action_handbook.number = actions_count

            try:
                new_action_handbook.save()
                # парсинг групп действий
                for action_group in action_groups:
                    actions = action_group['actions']
                    group_serial_number = action_group['action_group_serial_number']
                    action_group_name = action_group['action_group_name']

                    # парсинг действий в группе действий
                    for action in actions:

                        obj, created = Action.objects.update_or_create(
                            specification_action=new_action_handbook,
                            group_serial_number=group_serial_number,
                            action_serial_number=action['action_serial_number'],
                            defaults=dict(
                                group_name=action_group_name,
                                name=action['name'],
                                params1=action['parameters']['param1'],
                                params2=action['parameters']['param2'],
                                params3=action['parameters']['param3'],
                                params4=action['parameters']['param4'],
                                params5=action['parameters']['param5'],
                                params6=action['parameters']['param6'],
                                params7=action['parameters']['param7'],
                                params8=action['parameters']['param8'],
                                params9=action['parameters']['param9'],
                                params10=action['parameters']['param10']
                            )
                        )
                        # если происходит обновление, добавляем идентификатор обновляемого объекта в отслеживаемые
                        if exist_handbook_id:
                            edited_or_created_objects_ids.add(obj.pk)

                # если обновляется существующий объект - чистим бд от лишних групп действий / действий по этому объекту
                if exist_handbook_id:
                    exist_obj_ids = {action_obj.pk for action_obj in new_action_handbook.action_set.all()}
                    action_to_delete_ids = exist_obj_ids.difference(edited_or_created_objects_ids)
                    print('Удаленные действия / группы действий:', action_to_delete_ids)
                    Action.objects.filter(pk__in=action_to_delete_ids).delete()

                # проверка наличия дублирующихся имён групп или имён действий
                actions_obj = Action.objects.filter(specification_action=new_action_handbook)
                # список имён групп для данного справочника
                action_groups_names = actions_obj.distinct('group_serial_number').values_list('group_name', flat=True)
                # список кортежей (номер группы, имя действия) для данного справочника
                actions_names = actions_obj.values_list('group_serial_number', 'name')

                # если кол-во элементов query_set > кол-ва элементов множества значит есть повторения имён
                if action_groups_names.count() > len(set(action_groups_names)):
                    exc = APIException(
                        detail={'message': 'Ошибка сохранения - названия групп действий не должны повторяться.'})
                    exc.status_code = status.HTTP_409_CONFLICT
                    raise exc
                elif actions_names.count() > len(set(actions_names)):
                    exc = APIException(
                        detail={'message': 'Ошибка сохранения - названия действий в группе не должны повторяться.'})
                    exc.status_code = status.HTTP_409_CONFLICT
                    raise exc

                return Response(
                    {'message': f'Справочник действий успешно {"обновлён" if exist_handbook_id else "создан"}.'})

            except APIException as err:
                raise err
            except Exception as err:
                print(sys.exc_info())
                return Response({'message': str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            print(serializer.errors)
            return Response({'message': error_formatter(serializer.errors)}, status=status.HTTP_400_BAD_REQUEST)


class ActionHandbookToEdit(APIView, FormatterMixin):
    def get(self, request, action_handbook_id):
        """
        Метод для получения полной информации (в т.ч группы действий и действия) о существующем справочнике действий
        """
        action_handbook = get_object_or_404(SpecificationAction, pk=action_handbook_id, to_delete=False)
        try:
            result = self.action_handbook_form(action_handbook)
            result.update({'product_id': action_handbook.product_id})
            action_groups_objs_for_handbook = Action.objects.filter(specification_action=action_handbook).distinct(
                'group_serial_number')

            # лямбда - функция для формирования шаблона группы действий, на вход принимает объект модели Action
            action_form = lambda action_obj: {
                'action_serial_number': action_obj.action_serial_number,
                'name': action_obj.name,
                'parameters': {
                    'param1': action_obj.params1,
                    'param2': action_obj.params2,
                    'param3': action_obj.params3,
                    'param4': action_obj.params4,
                    'param5': action_obj.params5,
                    'param6': action_obj.params6,
                    'param7': action_obj.params7,
                    'param8': action_obj.params8,
                    'param9': action_obj.params9,
                    'param10': action_obj.params10
                }
            }

            result['action_groups'] = [
                {
                    'action_group_serial_number': action_group_obj.group_serial_number,
                    'action_group_name': action_group_obj.group_name,
                    'actions': [action_form(action_obj) for action_obj in
                                Action.objects.filter(
                                    specification_action_id=action_handbook_id,
                                    group_serial_number=action_group_obj.group_serial_number)
                                ]
                } for action_group_obj in action_groups_objs_for_handbook]
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения данных для редактирования справочника действий: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, action_handbook_id):
        """
        Метод для 'мягкого' удаления справочника действий
        """
        try:
            action_handbook = get_object_or_404(
                SpecificationAction.objects.filter(pk=action_handbook_id, to_delete=False))
            action_handbook.to_delete = True
            action_handbook.save()
            return Response({'message': 'Справочник действий успешно удалён'})
        except Exception as err:
            return Response({'message': f'Ошибка удаления справочника действий: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GoalsHandbooks(APIView, FormatterMixin):
    def goal_handbook_form(self, goal_handbook_obj):
        result = super().goal_handbook_form(goal_handbook_obj)
        result.update({'product_id': goal_handbook_obj.product_id,
                       'product_name': goal_handbook_obj.product.name,
                       'created': goal_handbook_obj.created_at.date(),
                       'goals_count': goal_handbook_obj.number})
        return result

    def get(self, request):
        """
        Метод получения данных для отображения карточек справочников целей
        """
        try:
            # объект-итератор с данными справочника целей (type: dict)
            result = map(self.goal_handbook_form, SpecificationPurpose.objects.filter(to_delete=False))
            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения справочников целей: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @transaction.atomic
    def post(self, request):
        """
        Метод для создания нового или обновления существующего справочника целей
        """
        serializer = NewGoalHandbook(data=request.data)
        if serializer.is_valid():
            exist_handbook_id, handbook_name, product_id, purpose_count, purpose_group = serializer.data.values()

            # проверка, не занято ли заданное пользователем имя для справочника целей для данного продукта
            if SpecificationPurpose.objects.filter(
                    name=handbook_name, product_id=product_id).exclude(pk=exist_handbook_id).exists():
                return Response({'message': 'Заданное имя справочника целей уже используется для данного продукта.'},
                                status=status.HTTP_409_CONFLICT)

            # если обновляем существующий объект
            if exist_handbook_id:
                new_goal_handbook = get_object_or_404(SpecificationPurpose, pk=exist_handbook_id, to_delete=False)
                # множество для отслеживания ID созданных или отредактированых наборов целей / целей
                edited_or_created_objects_ids = set()
            # если создаётся новый объект
            else:
                new_goal_handbook = SpecificationPurpose()
                new_goal_handbook.user_id = request.user.id

            new_goal_handbook.name = handbook_name
            new_goal_handbook.product_id = product_id
            new_goal_handbook.name = handbook_name
            new_goal_handbook.number = purpose_count

            try:
                new_goal_handbook.save()
                # парсинг групп целей
                for group in purpose_group:
                    purposes = group['purposes']
                    purpose_group_serial_number = group['purpose_group_serial_number']
                    # парсинг целей в группе
                    for purpose in purposes:
                        obj, created = Purpose.objects.update_or_create(
                            purpose_specification=new_goal_handbook,
                            group_serial_number=purpose_group_serial_number,
                            purpose_serial_number=purpose['purpose_serial_number'],
                            defaults={
                                'group_name': group['purpose_group_name'],
                                'purpose_id': purpose['purpose_id'],
                                'ym_name': purpose['ym_name'],
                                'final_name': purpose['final_name']}
                        )
                        # если редактируется существующий справочник целей
                        if exist_handbook_id:
                            # добавляем ID отредактированного / созданного объекта цели в множество редактируемых объектов
                            edited_or_created_objects_ids.add(obj.pk)

                # если редактируется существующий справочник целей - очищаем БД от лишних групп целей (если имеются)
                if exist_handbook_id:
                    # получаем множество существующих ID целей из БД
                    exist_purpose_obj_ids = {purpose_obj.pk for purpose_obj in new_goal_handbook.purpose_set.all()}
                    # получаем ID целей, которые не вернулись с фронтенда (были удалены) путём разности множеств
                    purpose_to_delete_ids = exist_purpose_obj_ids.difference(edited_or_created_objects_ids)
                    print('Удалённые группы целей / цели:', purpose_to_delete_ids)
                    # Удалёем лишние цели которые не вернулись с фронтенда из БД
                    Purpose.objects.filter(pk__in=purpose_to_delete_ids).delete()

                # проверка наличия дублирующихся имён групп или имён целей
                goals_obj = Purpose.objects.filter(purpose_specification=new_goal_handbook)
                # список имён целей для данного справочника
                goal_groups_names = goals_obj.distinct('group_serial_number').values_list('group_name', flat=True)
                # список кортежей (номер группы, имя цели) для данного справочника
                actions_names = goals_obj.values_list('group_serial_number', 'final_name')

                # если кол-во элементов query_set > кол-ва элементов множества значит есть повторения имён
                if goal_groups_names.count() > len(set(goal_groups_names)):
                    exc = APIException(
                        detail={'message': 'Ошибка сохранения - названия групп целей не должны повторяться.'})
                    exc.status_code = status.HTTP_409_CONFLICT
                    raise exc
                elif actions_names.count() > len(set(actions_names)):
                    exc = APIException(
                        detail={'message': 'Ошибка сохранения - названия целей в группе не должны повторяться.'})
                    exc.status_code = status.HTTP_409_CONFLICT
                    raise exc

                # возрат сообщения об обновлении (created=False) или создании (created=True) объекта obj
                return Response(
                    {'message': f'Справочник целей успешно {"создан" if not exist_handbook_id else "обновлён"}.'})

            except APIException as err:
                raise err

            except Exception as err:
                print(sys.exc_info())
                return Response({'message': str(err)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response(error_formatter(serializer.errors), status=status.HTTP_400_BAD_REQUEST)


class GoalHandbookToEdit(APIView, FormatterMixin):
    def get(self, request, goal_handbook_id):
        """
        Метод для получения полной информации (в т.ч группы, цели) о конкретном справочнике целей
        """
        goal_handbook = get_object_or_404(SpecificationPurpose, pk=goal_handbook_id, to_delete=False)
        try:
            # формирование тела ответа
            result = self.goal_handbook_form(goal_handbook)
            result.update({'product_id': goal_handbook.product_id})
            goals_groups_for_handbook = Purpose.objects.filter(purpose_specification=goal_handbook)
            result['purpose_groups'] = [{
                'purpose_group_serial_number': goal_group_obj.group_serial_number,
                'purpose_group_name': goal_group_obj.group_name,
                'purposes': [
                    {
                        'purpose_serial_number': purpose.purpose_serial_number,
                        'purpose_id': purpose.purpose_id,
                        'final_name': purpose.final_name,
                        'ym_name': purpose.ym_name} for purpose in Purpose.objects.filter(
                        group_serial_number=goal_group_obj.group_serial_number,
                        purpose_specification_id=goal_handbook_id
                    )]
            } for goal_group_obj in goals_groups_for_handbook.distinct('group_serial_number')]

            return Response(result)
        except Exception as err:
            return Response({'message': f'Ошибка получения данных для редактирования продукта: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, goal_handbook_id):
        """Метод для 'мягкого' удаления справочника целей"""
        try:
            goal_handbook = get_object_or_404(SpecificationPurpose, pk=goal_handbook_id, to_delete=False)
            goal_handbook.to_delete = True
            goal_handbook.save()
            return Response({'message': 'Справочник целей успешно удалён'})
        except Exception as err:
            return Response({'message': f'Ошибка удаления справочника целей: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class YDCampaigns(APIView):
    @method_decorator(cache_page(60 * 60 * 3))  # кеширование ответа на 3 часа
    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id, to_delete=False)
        yd_login = product.yd_login

        # API Яндекс Директа
        yd_api_url = 'https://api.direct.yandex.com/json/v5/campaigns'
        # Сторонний (дополнительный) API для получения кампаний
        outer_api_url = f"https://direct.yandex.ru/web-api/grid/api?operationName=GridCampaigns&ulogin={yd_login}"

        # проверка наличия авторизационных токенов в переменных среды
        if not YD_AUTH_TOKEN or not YM_AUTH_TOKEN:
            return Response({
                'message': 'Не предоставлены авторизационные токены Яндекс-API. Пожалуйста, обратитесь к администратору.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        try:
            # чтение файла-конфигурации для выполнения запроса к API Яндекс Директа
            with open(os.path.join(BASE_DIR, 'products_report_generator_api', 'yd_api_config.json'),
                      encoding='utf-8') as config_file:
                config = json.load(config_file)

                # получаем json-строку (str)
                yd_api_headers = json.dumps(config['yd_api_headers'])
                # меняем заполнители {{token}} и {{login}} на реальные токен и логин Яндекс Директ
                yd_api_headers = yd_api_headers.replace('{{token}}', YD_AUTH_TOKEN).replace('{{login}}', yd_login)
                # приводим json-строку обратно в python-объект
                yd_api_headers = json.loads(yd_api_headers)

                # нет заполнителей - ничего не меняем
                yd_api_body = config['yd_api_body']

                outer_api_headers = json.dumps(config['outer_api_headers'])
                # меняем заполнители {{yd_login}} на действительный логин Яндекс Директ
                request_headers = outer_api_headers.replace('{{yd_login}}', yd_login)
                request_headers = json.loads(request_headers)

                outer_api_payload = json.dumps(config['outer_api_payload'])
                # меняем заполнители {{yd_login}} на действительный логин Яндекс Директ
                payload = outer_api_payload.replace('{{yd_login}}', yd_login)
                payload = json.loads(payload)

            cookies = self.load_cookies_from_minio()
            headers = self.update_headers_with_csrf(request_headers, cookies)

            yd_api_response = requests.post(yd_api_url, json=yd_api_body, headers=yd_api_headers)
            outer_api_response = requests.post(outer_api_url, headers=headers, cookies=cookies, json=payload)

            # обработка ошибок ответов от API Яндекс Директ
            # ошибка запроса по некорректному логину
            if 'error' in yd_api_response.json() and outer_api_response.json()['text'] == 'No rights':
                return Response({
                    'message': f'Не удалось получить кампании Я.Директа для продукта "{product.name}" - некорректный логин кабинета Яндекс Директ.'},
                    status=status.HTTP_404_NOT_FOUND)

            # ошибка запроса (наиболее вероятно, истёк один из токенов)
            elif outer_api_response.status_code != 200 or yd_api_response.status_code != 200:
                # ссылка на скрипт Стёпы для обновления куки
                if outer_api_response.status_code in (401, 403):
                    return Response({
                        'message': f'Не удалось получить кампании ЯД. Требуется обновление csrf-токена (куки). '
                                   f'Ссылка для скачивания файла и инструкции для обновления: '
                                   f'https://www.upk-mos.ru/minio/dit-services-dev/cookies_for_campaigns/update_cookie.zip'
                    }, status=401)

                elif yd_api_response == 401:
                    return Response({'message': 'Истек авторизационный токен API Я.Директ'},
                                    status=status.HTTP_403_UNAUTHORIZED)

                else:
                    return Response(
                        {
                            'message': f'Ошибка получения кампаний Яндекс Директ. yd_api status_code={yd_api_response.status_code},'
                                       f'outer_yd_api status_code={outer_api_response.status_code}'},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            api_yd_campaigns = yd_api_response.json().get('result').get('Campaigns')
            outer_yd_campaigns = outer_api_response.json()
            outer_yd_campaigns = outer_yd_campaigns.get('data').get('client').get('campaigns').get('rowset')

            # формирование первичной схемы ответа из кампания ЯД полученных из внешнего API
            result = [{
                'id': yd_campaign_obj['id'],
                'name': yd_campaign_obj['name'],
                'status': yd_campaign_obj['status']['primaryStatus']
            } for yd_campaign_obj in outer_yd_campaigns]

            # приводим форму статусов полученных кампаний к единому формату
            self.mappings_statuses(result)

            # добавляем к перивичной схеме ответа остальные кампании ЯД полученных из API ЯД
            result.extend([{'id': str(yd_campaign_obj['Id']), 'name': yd_campaign_obj['Name'],
                            'status': yd_campaign_obj['StatusClarification']} for yd_campaign_obj in api_yd_campaigns])

            return Response({'yd_campaigns': result})

        except Exception as err:
            return Response(
                {
                    'message': f'Ошибка получения кампаний Яндекс Директа для логина "{yd_login}" продукта "{product.name}": {str(err)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def load_cookies_from_minio(self, bucket_name=BUCKET_NAME, object_name="cookies_for_campaigns/user_1_cookies.json"):
        response = storage.client.get_object(bucket_name, object_name)
        data = response.read().decode("utf-8")
        response.close()
        response.release_conn()
        return json.loads(data)

    def update_headers_with_csrf(self, headers: dict, cookies: dict) -> dict:
        """
        Берём CSRF токен из cookies["_direct_csrf_token"] и подставляем в headers["x-csrf-token"]
        """
        csrf_token = cookies.get("_direct_csrf_token")
        if csrf_token:
            headers["x-csrf-token"] = csrf_token
        return headers

    def mappings_statuses(self, outer_yd_campaigns):
        """
        Функция приводит статусы кампаний ЯД, полученных из внешнего API
        к формату статусов кампаний ЯД, полученных из API ЯД
        """
        # известные статусы кампаний ЯД из внешнего API ЯД
        CAMPAIGN_STATUSES = {
            'ACTIVE': 'Идут показы',
            'STOPPED': 'Кампания остановлена',
            'ARCHIVED': 'Кампания перенесена в архив'
        }

        for campaign_obj in outer_yd_campaigns:
            campaign_obj['status'] = CAMPAIGN_STATUSES[campaign_obj['status']]


class YMGoals(APIView):
    def get(self, request, product_id):
        product = get_object_or_404(Product, pk=product_id)
        ym_counter = product.ym_counter

        url = f'https://api-metrika.yandex.net/management/v1/counter/{ym_counter}/goals/'
        headers = {'Authorization': YM_AUTH_TOKEN}
        try:
            request = requests.get(url, headers=headers)

            if request.status_code == 404:
                return Response(
                    {
                        'message': f'Не удалось получить цели для продукта "{product.name}" - некорректный номер счётчика Яндекс Метрики.'},
                    status=status.HTTP_404_NOT_FOUND)

            elif request.status_code == 403:
                return Response(
                    {
                        'message': f'Не удалось получить цели для продукта "{product.name}" - отказ в доступе.'},
                    status=status.HTTP_403_FORBIDDEN)

            elif request.status_code == 401:
                return Response(
                    {'message': 'Авторизационный токен Яндекс Метрики истёк. Обратитесь к администратору.'},
                    status=status.HTTP_403_FORBIDDEN)

            result = request.json()
            for i in range(len(result['goals'])):
                result['goals'][i] = {'id': result['goals'][i]['id'], 'name': result['goals'][i]['name']}

            return Response(result)

        except Exception as err:
            return Response({'message': f'Ошибка получения целей Яндекс Метрики: {str(err)}'},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
