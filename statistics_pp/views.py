import io

from django.shortcuts import render, get_object_or_404
from django.db.utils import IntegrityError
from django.db.models import ObjectDoesNotExist
from rest_framework.response import Response
from rest_framework.exceptions import status, APIException
from rest_framework.views import APIView

from .serializers import ProviderParameters, NewSegment
from .models import Metric, RegionCodifier, OKPD2Codifier, Segment, OKPD2, Process, Region
from core.minio_storage import storage


# Create your views here.
class DefaultException(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = 'Ошибка параметров'


class ProviderStatistic(APIView):
    def post(self, request):
        """
        Конечная точка для создания процесса (задачу) сбора статистики
        """
        parameters = ProviderParameters(data=request.data)
        if parameters.is_valid():
            okpd2_codifier_ids = parameters.validated_data['okpd2']
            metrics = parameters.validated_data['metrics']

            region_ids = parameters.validated_data['regions']
            region_codifier_ids = [r.id for r in RegionCodifier.objects.filter(region_id__in=region_ids)]

            process = Process()
            okpd2_objs = [OKPD2.objects.get(code=ids) for ids in okpd2_codifier_ids]
            okpd2_ids = [okpd2.id for okpd2 in okpd2_objs]
            process.okpd2_ids = okpd2_ids
            process.region_ids = region_codifier_ids

            # формирование массива из 3-х элементов (значения только 0 или 1) где каждый элемент отвечает за -
            # arr[0] - количество контрактов arr[1] - предложений всего arr[2] предложений активных
            process.metrics = metrics
            validate_metrics = [0 for i in range(3)]
            for ind in metrics:
                validate_metrics[ind - 1] = 1

            process.metrics = validate_metrics
            process.save()

            request_id = process.pk
            return Response({'status_code': status.HTTP_200_OK, 'request_id': request_id, 'message': 'Успех'})
        else:
            print(parameters.errors)
            raise DefaultException(detail='Ошибка валидации параметров запроса')


class GetMetricsRegions(APIView):
    def get(self, request):
        """
        Выдаёт метрики и регионы из БД
        """
        raw_metrics = Metric.objects.all()
        raw_regions = RegionCodifier.objects.all()
        metrics = [{'id': m.id, 'metric_name': m.name} for m in raw_metrics]
        regions = [{'region_code': r.region_code, 'name': r.region_name, 'region_id': r.region_id} for r in raw_regions]
        result = {'metrics': metrics, 'regions': regions}

        return Response(result)


class GetOkpd2Segments(APIView):
    def get(self, request):
        """
        Выдаёт ОКПД2-коды и пользовательские сегменты из БД
        """
        raw_okpd_queryset = OKPD2Codifier.objects.all()
        raw_segments_queryset = Segment.objects.all()

        result = {
            'segments': [{'id': segment.id, 'segment_name': segment.name} for segment
                         in raw_segments_queryset],
            'okpd2': [{'id': okpd.id, 'code': okpd.code, 'description': okpd.description} for okpd in
                      raw_okpd_queryset.filter(parent_id=0)],
        }

        return Response(result)


"""    def children_placeholder(self, base_layer, raw_okpd_queryset):
        # Заполняет массив children для каждого объекта ОКПД2-кода начиная с базового (parent_id=0) уровня
        for d in base_layer:
            chields = raw_okpd_queryset.filter(parent_id=d['id'])
            if chields:
                new_chields = list(
                    {'id': item.id, 'code': item.code, 'description': item.description, 'chields': []} for item in
                    chields)
                d['chields'].extend(new_chields)
                self.children_placeholder(new_chields, raw_okpd_queryset)"""


class GetChieldForOkpd2(APIView):
    def get(self, request, parent_id):
        try:
            okpd2_parent = OKPD2Codifier.objects.get(id=parent_id)
        except ObjectDoesNotExist:
            raise DefaultException(detail='Объекта с данным ID не найдено')
        chields = OKPD2Codifier.objects.filter(parent_id=parent_id)
        result = [{'id': okpd.id, 'code': okpd.code, 'description': okpd.description} for okpd in chields]

        return Response(result)


class CreateSegment(APIView):
    def post(self, request):
        """
        конечная точка для создания сегмента
        """
        segment_data = NewSegment(data=request.data)
        if segment_data.is_valid():
            segment_name, okpd2_array = segment_data.validated_data.values()
            if Segment.objects.filter(name=segment_name).exists():
                raise DefaultException(detail='Имя сегмента уже существует')
            else:
                segment_name, okpd2_array = segment_data.validated_data.values()
                segment = Segment.objects.create(name=segment_name)
                okpd2_objects_for_id = [OKPD2.objects.get(code=i) for i in okpd2_array]
                segment.okpd2_set.add(*okpd2_objects_for_id)
                return Response({'status_code': status.HTTP_200_OK, 'message': 'Успех'})
        else:
            raise DefaultException(detail='Ошибка валидации параметров запроса')


class GetProcess(APIView):
    def get(self, request, request_id):
        """
        Выдаёт статус выполнения существующего запроса (% выполнения | file_url)
        """
        process = get_object_or_404(Process, pk=request_id)
        if process.error_msg:
            print(process.error_msg)
            exc = DefaultException(detail='При формировании статистики произошла ошибка. Попробуйте повторить запрос.')
            exc.status_code = status.HTTP_502_BAD_GATEWAY
            raise exc

        progress = process.progress
        file_url = None
        file_name = None

        if process.progress == 100:
            if process.data_file:
                file_url = storage.share_file_from_bucket(process.data_file)
                file_name = process.data_file.split('/')[-1]
            else:
                progress = 99

        return Response({'status_code': status.HTTP_200_OK,
                         'progress': progress,
                         'file_url': file_url,
                         'file_name': file_name,
                         'message': 'Успех'})


class GetSegmentData(APIView):
    def get(self, request, segment_id):
        """
        Выдаёт данные ОКПД2 кодов по ID сегмента
        """
        try:
            segment = Segment.objects.get(id=segment_id)
        except ObjectDoesNotExist:
            raise DefaultException(detail='Сегмента с данным ID не существует')

        # принимает массив объектов OKPD2Codifier и возвращает их данные в формате словаря
        format_okpd2codes_for_segment = lambda okpd2_codifier_objects: [{'id': okpd2_code.id,
                                                                         'code': okpd2_code.code,
                                                                         'description': okpd2_code.description} for
                                                                        okpd2_code in okpd2_codifier_objects]
        okpd2_codifier_objects = [OKPD2Codifier.objects.get(id=okpd2.code) for okpd2 in segment.okpd2_set.all()]
        result = format_okpd2codes_for_segment(okpd2_codifier_objects)
        return Response({'dict_okpd2_objects': result})

    def get_path(self, segment):
        """
        Возвращает массив содержащий ID окпд2 кодов
        представляющих собой путь к окпд2 коду в виде иерархической структуры
        """
        raw_okpd_queryset = OKPD2Codifier.objects.all()
        paths = []  # хранит пути к родителям ОКПД2 кодов
        for okpd_code in OKPD2Codifier.objects.filter(id__in=[okpd.code for okpd in segment.okpd2_set.all()]).distinct(
                'parent_id'):
            path_for_okpd2code = self.parent_placeholder(okpd_code, raw_okpd_queryset)
            paths.append(path_for_okpd2code)
        return paths

    def parent_placeholder(self, okpd2_code, raw_okpd_queryset, array=[]):
        """
        Возвращает массив содержащий путь в виде множества ID окпд2-кодов от родительского к дочернему
        """
        okpd2_obj = OKPD2Codifier.objects.get(pk=okpd2_code.id)
        if okpd2_obj.parent_id != 0:
            parent_okpd2_obj = OKPD2Codifier.objects.get(id=okpd2_obj.parent_id)
            array.append(okpd2_obj.id)
            self.parent_placeholder(parent_okpd2_obj, raw_okpd_queryset, array)
        else:
            array.append(okpd2_obj.id)
            array.reverse()
        return array
