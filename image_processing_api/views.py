import logging
import traceback

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers
from drf_spectacular.utils import extend_schema, inline_serializer
from dotenv import load_dotenv

from .serializers import Request
from image_processing_api.FileProcessor import FileProcessor

load_dotenv()

logging.basicConfig(level=logging.INFO, format='[{asctime}] #{levelname:4} {name}:{lineno} - {message}', style='{',
                    encoding='utf-8')
logger = logging.getLogger(__name__)


# Create your views here.
class NewRequest(APIView):
    """
    Принимает в обработку изображение или архив с изображениями
    """
    serializer_class = Request

    @extend_schema(responses={
        200: inline_serializer(
            name='SuccessResponse',
            fields={
                "file_name": serializers.CharField(help_text='имя файла'),
                "file_url": serializers.CharField(help_text='путь для скачивания файла')
            }
        ),
        400: inline_serializer(
            name='ErrorResponse',
            fields={
                "message": serializers.CharField(help_text='описание ошибки')
            }
        )
    })
    def post(self, request):
        try:
            data = Request(data=request.data)
            if data.is_valid():
                print(data.validated_data)
                file_processor = FileProcessor(data.validated_data)
                file_url = file_processor.start_processing()
                logger.info('Обработка завершена.')
                return Response({
                    "file_name": file_processor.output_filename,
                    "file_url": file_url
                })
            else:
                return Response({'message': 'Ошибка валидации',
                                 'detail': {k: ', '.join(v) for k, v in data.errors.items()}},
                                status=status.HTTP_400_BAD_REQUEST)
        except Exception as err:
            print(traceback.format_exc())
            return Response({"message": f"Ошибка сервера: {err}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
