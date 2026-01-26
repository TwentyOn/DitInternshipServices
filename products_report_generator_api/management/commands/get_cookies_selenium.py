from django.core.management.base import BaseCommand
import json
import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from minio import Minio
import os
import io
from dit_services.minio_storage import storage


TARGET_URL = (
    "https://direct.yandex.ru/dna/grid/campaigns/?ulogin=e-20035215"
    "&dim-filter=CPC_AND_CPM&status-filter=ALL_EXCEPT_ARCHIVED"
    "&stat-preset=last365Days&filter=metaTypes+%3D+UC_TEXT"
)
OUT_FILE = Path("cookies.json")
HEADLESS = False
WAIT_TIMEOUT = 300
POLL_INTERVAL = 1.0

class Command(BaseCommand):
    def handle(self, *args, **options):
        self.main()

    def main(self):
        print("Запуск браузера...")
        driver = self.start_driver(HEADLESS)
        try:
            print("Открываю:", TARGET_URL)
            driver.get(TARGET_URL)
            start_ts = time.time()

            time.sleep(1.0)

            if self.is_direct_page_loaded(driver):
                print("Похоже уже авторизованы и страница загружена.")
                self.collect_and_save_cookies(driver, OUT_FILE)
                return

            print("Похоже, требуется авторизация. Войдите вручную в открывшемся окне браузера.")
            print(f"Ожидание авторизации (таймаут {WAIT_TIMEOUT} сек)...")
            while time.time() - start_ts < WAIT_TIMEOUT:
                time.sleep(POLL_INTERVAL)
                if self.is_direct_page_loaded(driver):
                    print("Определена загрузка страницы campaigns.")
                    self.collect_and_save_cookies(driver, OUT_FILE)
                    return

            print("Таймаут ожидания авторизации истёк. Сохраняем текущие cookies (если есть).")
            self.collect_and_save_cookies(driver, OUT_FILE)
            print("Если файл не содержит ожидаемых cookie — повторите логин вручную и запустите снова.")
        except KeyboardInterrupt:
            print("Interrupted by user — сохраняем имеющиеся cookies.")
            try:
                self.collect_and_save_cookies(driver, OUT_FILE)
            except Exception:
                pass
        except Exception as exc:
            print("Ошибка:", exc)
            try:
                self.collect_and_save_cookies(driver, OUT_FILE)
            except Exception:
                pass
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def start_driver(self, headless: bool):
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1600,1000")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver

    def save_cookies_to_minio(self, cookies: dict, bucket_name="dit-services-dev",
                              object_name="cookies_for_campaigns/cookies.json"):
        data = json.dumps(cookies, ensure_ascii=False).encode("utf-8")
        data_stream = io.BytesIO(data)

        storage.client.put_object(
            bucket_name,
            object_name,
            data_stream,
            length=len(data),
            content_type="application/json"
        )

    def collect_and_save_cookies(self, driver, out_path: Path):
        raw = driver.get_cookies()
        flat = {}
        for c in raw:
            name = c.get("name")
            value = c.get("value")
            if name is None:
                continue
            flat[name] = value

        self.save_cookies_to_minio(flat)
        # out_path.write_text(json.dumps(flat, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_direct_page_loaded(self, driver) -> bool:
        try:
            url = driver.current_url or ""
            if "/dna/grid/campaigns" in url:
                return True
            elems = driver.find_elements(By.CSS_SELECTOR, "[data-test='campaigns-grid'], .campaigns-grid, div.grid")
            if elems:
                return True
        except Exception:
            pass
        return False