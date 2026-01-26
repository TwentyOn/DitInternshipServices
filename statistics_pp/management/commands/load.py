import re, os
from statistics_pp.models import OKPD2, OKPD2Codifier, Region, RegionCodifier
import csv
from django.core.management.base import BaseCommand

OKPD2_CSV_PATH = r'D:\PycharmProjects\DitServicesTest\backend\statistics_pp\management\commands\data\okpd2_202509041307.csv'
OKPD_CODIFIER_PATH = os.path.normpath(
    r'D:\PycharmProjects\DitServicesTest\backend\statistics_pp\management\commands\data\okpd2_codifier_202509041308.csv')
REGIONS_CSV_PATH = r'D:\PycharmProjects\image_converter\statistics_pp\management\commands\data\regions_202508281237.csv'
REGIONS_CODENTIFIER_PATH = r'D:\PycharmProjects\image_converter\statistics_pp\management\commands\data\regions_codifier_202508281027.csv'


class Command(BaseCommand):
    def handle(self, *args, **options):
        # self.load_okpd2_from_csv()
        # self.load_okpd_codifier_from_csv()
        # self.load_regions_from_csv()
        # self.load_regions_codifier_from_csv()

    def load_okpd2_from_csv(self, path=OKPD2_CSV_PATH):
        count = 0

        with open(path, 'r', encoding='utf-8') as csv_file:
            data = csv.reader(csv_file)
            next(data)  # пропуск шапки csv
            for pk, code, description in data:
                count += 1
                OKPD2.objects.create(id=pk, code=code, description=description)
            print('Успешно добавлено', count, 'записей в модель:', OKPD2.__name__)

    def load_okpd_codifier_from_csv(self, path=OKPD_CODIFIER_PATH):
        count = 0
        with open(path, encoding='utf-8') as csv_file:
            data = csv.reader(csv_file)
            next(data)
            for pk, code, description, parent_id, active in csv.reader(csv_file):
                count += 1
                OKPD2Codifier.objects.create(id=pk, code=code, description=description, parent_id=parent_id,
                                             active=True if active == 'true' else False)
            print('Успешно добавлено', count, 'записей в модель:', OKPD2Codifier.__name__)

    def load_regions_from_csv(self, path=REGIONS_CSV_PATH):
        count = 0
        with open(path, encoding='utf-8') as csv_file:
            data = csv.reader(csv_file)
            next(data)
            for _, region_code, region_name in csv.reader(csv_file):
                count += 1
                Region.objects.create(region_code=region_code, region_name=region_name)
            print('Успешно добавлено', count, 'записей в модель:', Region.__name__)

    def load_regions_codifier_from_csv(self, path=REGIONS_CODENTIFIER_PATH):
        count = 0
        with open(path, encoding='utf-8') as csv_file:
            data = csv.reader(csv_file)
            next(data)
            for _, region_code, region_name, region_id in csv.reader(csv_file):
                count += 1
                # print(region_code, region_name, region_id)
                RegionCodifier.objects.create(region_code=region_code, region_name=region_name, region_id=region_id)
            print('Успешно добавлено', count, 'записей в модель:', RegionCodifier.__name__)
