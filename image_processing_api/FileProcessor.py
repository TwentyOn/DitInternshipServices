import io
import os
import traceback
from zipfile import ZipFile
import logging
from datetime import date, datetime

from django.core.files.uploadedfile import TemporaryUploadedFile
from django.conf import settings
from dotenv import load_dotenv
from PIL import Image
from cairosvg import svg2png, svg2svg
from cairosvg.parser import Tree

from core.minio_storage import storage
from .serializers import ALLOWED_EXTENSIONS

load_dotenv()
logger = logging.getLogger(__file__)

# папка для сохранения результатов обработки
RESULTS_DIR = os.path.join(settings.BASE_DIR, 'media', 'image_processing_results')



class ImageProcessor:
    def __init__(self, image_file: bytes, filename: str, request_data):
        """
        Класс для обработки одиночного изображения
        :param image_file: файл изображения
        :param filename: имя файла
        :param request_data:
        """
        self.__image_file: io.BytesIO = io.BytesIO(image_file)
        self.filename: str = filename
        self.__request_data = request_data

        # pillow не имеет формата jpg, меняем  на jpeg
        if self.__request_data['format'] == 'jpg':
            self.__request_data['format'] = 'jpeg'

    @property
    def image_file(self):
        self.__image_file.seek(0)
        return self.__image_file

    def process_image(self) -> io.BytesIO:
        """
        Главные метод для старта обработки изображения
        :return:
        """
        logger.info(f'Обработка изображения {self.filename}...')
        if self.filename.endswith('.svg'):
            if self.__request_data.get('vector'):
                logger.info(f'Сохранение без изменений...')
                return self.image_file
            elif self.__request_data['format'] != 'original':
                processed_file = self._vector2rastr(self.image_file)
                processed_file = self._rastr_process(processed_file)
                return processed_file

            processed_file = self._vector_process()
            return processed_file
        elif self.filename.endswith(('.ai', '.eps')):
            logger.info(f'Сохранение без изменений...')
            return self.image_file
        else:
            processed_file = self._rastr_process(self.image_file)
            return processed_file

    def _vector_process(self) -> io.BytesIO:
        """
        Обработка вектороной графики
        :return:
        """
        logger.info('Обработка векторного изображения...')
        output_file = io.BytesIO()

        if not self.__request_data['resolution']:
            if self.__request_data['proportion']:
                svg_data = Tree(bytestring=self.image_file.read())
                # МОЖНО ВОСПОЛЬЗОВАТЬСЯ СВОЙСТВОМ ЧТОБЫ КАЖДЫЙ РАЗ ПРИ ЧТЕНИИ ВЫЗВАЛСЯ SEEK(0)
                self.image_file.seek(0)
                new_width, new_height = self._get_proportion_size(svg_data.get('width'), svg_data.get('height'))
            else:
                new_width = self.__request_data['width']
                new_height = self.__request_data['height']

            logger.info(f'Сохранение с изменением размеров {new_width}x{new_height}...')
            svg2svg(file_obj=self.image_file, output_width=new_width, output_height=new_height, write_to=output_file)

        else:
            logger.info(f'Сохранение без изменений...')
            svg2svg(file_obj=self.image_file, write_to=output_file)
        output_file.seek(0)
        return output_file

    def _rastr_process(self, image_file):
        """
        Обработка растровой графики
        :param image_file:
        :return:
        """
        logger.info('Обработка растрового изображения...')
        output_file = io.BytesIO()
        image = Image.open(image_file)

        fmt = self.__request_data.get('format')
        if fmt != 'original':
            current_extension = self.filename.split('.')[-1]
            self.filename = self.filename.replace(f'.{current_extension}', f'.{fmt}')

        quality = self.__request_data.get('quality')

        if not self.__request_data.get('resolution'):
            if self.__request_data.get('proportion'):
                width, height = self._get_proportion_size(*image.size)
            else:
                width, height = self.__request_data.get('width'), self.__request_data.get('height')
            image = image.resize((width, height))

        save_fmt = fmt if fmt.lower() != 'original' else self.filename.split('.')[-1]

        logger.info(f'Сохранение в формате {save_fmt}, качестве {quality}% ...')

        if image.mode == "RGBA" and save_fmt.lower() == "jpeg":
            image = image.convert("RGB")

        image.save(output_file, quality=int(quality), format=save_fmt)
        image.close()
        output_file.seek(0)

        return output_file

    def _get_proportion_size(self, original_width, original_height):
        """
        Расчёт размеров изображения с сохранением пропорций
        :param original_width:
        :param original_height:
        :return:
        """
        original_height = ''.join(filter(lambda x: x.isdigit(), str(original_height)))
        original_width = ''.join(filter(lambda x: x.isdigit(), str(original_width)))

        logger.info('Меняю разрешение с сохранением пропорций...')
        aspect_ratio = int(original_width) / int(original_height)  # пропорции
        # если False редактируется высота (считаем ширину)
        if not self.__request_data["toggle_switch"]:
            new_width = int(self.__request_data['height'] * aspect_ratio)
            new_height = self.__request_data['height']
        # если True редактируется ширина (считаем высоту)
        else:
            new_width = self.__request_data['width']
            new_height = int(self.__request_data['width'] / aspect_ratio)

        logger.info(f'Новый размер: {new_width}x{new_height}')
        return new_width, new_height

    def _vector2rastr(self, image_file):
        """
        Конвертирование svg-формата в растровый тип изображения
        :return:
        """
        logger.info('Конвертация векторного изображения в растровое...')
        if self.__request_data.get('vector'):
            return image_file
        else:
            png_file = io.BytesIO()
            svg2png(file_obj=image_file, write_to=png_file, dpi=300)
            png_file.seek(0)
            return png_file


class FileProcessor:
    """
    Получает на вход файл, обрабатывает в зависимости от типа (zip или одиночное изображение)
    """

    def __init__(self, request_data):
        self.file: TemporaryUploadedFile = request_data.get('file')
        self.output_filename = None
        self.request_data = request_data

    def start_processing(self):
        """
        Центральный метод для старта обработки
        :return:
        """
        processed_filepath = None
        if not os.path.exists(RESULTS_DIR):
            os.makedirs(RESULTS_DIR)

        try:
            if self.is_zip():
                processed_filepath = self.zip_processing()
            else:
                processed_filepath = self.image_processing()
            self.output_filename = processed_filepath.split(os.sep)[-1]

            s3path = self.upload_zip2s3(processed_filepath)

            return s3path
        finally:
            if processed_filepath:
                os.remove(processed_filepath)

    def zip_processing(self) -> str:
        """
        Обработка zip-архива
        :return:
        """
        datatime_mark = datetime.now().strftime('%Y%m%d_%H%M%S-%f')
        output_zip_name = f'{datatime_mark}_{self.file.name.replace(" ", "_")}'
        output_zip_path = os.path.join(RESULTS_DIR, output_zip_name)

        with ZipFile(self.file) as zipfile, ZipFile(output_zip_path, 'w') as output_zip:
            for i in zipfile.infolist():
                if i.filename.endswith(tuple(ALLOWED_EXTENSIONS)):
                    image_processor = ImageProcessor(zipfile.read(i.filename), i.filename, self.request_data)
                    file = image_processor.process_image()
                    output_zip.writestr(self.encode_broken_name(image_processor.filename), file.getvalue())
                else:
                    output_zip.writestr(self.encode_broken_name(i.filename), zipfile.read(i.filename))

        return output_zip_path

    def image_processing(self) -> str:
        image_processor = ImageProcessor(self.file.read(), self.file.name, self.request_data)
        prefix = str(datetime.now().timestamp()).replace('.', '') + '_'

        processed_image = image_processor.process_image()
        processed_filename = image_processor.filename.replace(' ', '_')
        processed_filename = prefix + processed_filename

        processed_file_path = os.path.join(RESULTS_DIR, processed_filename)

        with open(processed_file_path, 'wb') as f:
            f.write(processed_image.read())

        return processed_file_path

    def is_zip(self):
        """
        Проверка на тип файла
        :return:
        """
        filename: str = self.file.name
        return filename.endswith('.zip')

    def encode_broken_name(self, name):
        """
        Функция для корректного отображения кирилицы в названии zip-файлов
        :param name: название zip-файла
        :return: строка
        """
        try:
            return bytes(name, "CP437").decode("cp866")
        except:
            return name

    @staticmethod
    def upload_zip2s3(filepath):
        """
        Отправляет файл в S3-хранилище
        :param filename:
        :param filepath:
        :return:
        """
        logger.info(f'Отправка файла {filepath} в хранилище...')
        filename = filepath.split(os.sep)[-1]
        s3path = f'image_processing/{filename}'
        for iteration in range(3):
            try:
                storage.upload_file(s3path, filepath, os.getenv('S3_BUCKET_NAME'))
                logger.info(f'Файл отправлен: {s3path}.')
                file_url = storage.share_file_from_bucket(s3path)
                return file_url
            except Exception as err:
                logger.error(f'Не удалось отправить файл в хранилище: {err}')
                if iteration - 1 == 2:
                    raise IOError(f'Не удалось отправить файл в хранилище: {err}')
                else:
                    continue
