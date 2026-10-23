"""Клиент открытого API портала «Работа России» (opendata.trudvsem.ru).

Документация: https://trudvsem.ru/opendata/api
Ключ не нужен. За один запрос отдаётся не больше 100 вакансий,
параметр offset — это номер страницы, а не смещение в записях.
"""

import logging
import time
from collections.abc import Iterator

import requests

BASE_URL = "https://opendata.trudvsem.ru/api/v1/vacancies"
PAGE_SIZE = 100
RETRY_STATUSES = {429, 500, 502, 503, 504}

log = logging.getLogger(__name__)


class ApiError(Exception):
    """API вернул ошибку, которую нет смысла повторять."""


class TrudvsemClient:
    def __init__(self, delay: float = 0.5, retries: int = 3, timeout: float = 30):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "vacancy-parser/1.0"

    def _get(self, url: str, params: dict) -> dict:
        """GET-запрос с повтором при сетевых ошибках и перегрузке сервера."""
        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                error = f"сетевая ошибка: {exc}"
            else:
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRY_STATUSES:
                    raise ApiError(f"HTTP {response.status_code}: {response.text[:200]}")
                error = f"HTTP {response.status_code}"

            if attempt == self.retries:
                raise ApiError(f"не удалось получить данные после {self.retries} попыток ({error})")
            wait = 2**attempt
            log.warning("Попытка %d/%d: %s, жду %d с", attempt, self.retries, error, wait)
            time.sleep(wait)

        raise AssertionError("недостижимо")

    def search(self, text: str, region: str | None = None, max_pages: int = 5) -> Iterator[dict]:
        """Отдаёт сырые вакансии по запросу, страница за страницей."""
        url = f"{BASE_URL}/region/{region}" if region else BASE_URL
        total_pages = None

        for page in range(max_pages):
            data = self._get(url, {"text": text, "limit": PAGE_SIZE, "offset": page})
            vacancies = data.get("results", {}).get("vacancies", [])

            if total_pages is None:
                total = data.get("meta", {}).get("total", 0)
                total_pages = min(max_pages, -(-total // PAGE_SIZE))
                log.info("Найдено вакансий: %d, будет загружено страниц: %d", total, total_pages)

            if not vacancies:
                break

            log.info("Страница %d/%d: получено %d вакансий", page + 1, total_pages, len(vacancies))
            for item in vacancies:
                yield item["vacancy"]

            if page + 1 >= total_pages:
                break
            time.sleep(self.delay)
