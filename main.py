"""Сбор вакансий с портала «Работа России» и выгрузка отчёта в Excel.

Пример:
    python main.py --query "python разработчик" --region moscow --pages 5
"""

import argparse
import logging
import re
import sys
from datetime import date
from pathlib import Path

from excel_report import build_report
from transform import prepare
from trudvsem_client import ApiError, TrudvsemClient

# Коды регионов в API — 13 цифр (код КЛАДР). Здесь самые частые, остальные можно передать кодом.
REGIONS = {
    "moscow": ("7700000000000", "Москва"),
    "spb": ("7800000000000", "Санкт-Петербург"),
    "mo": ("5000000000000", "Московская область"),
    "kazan": ("1600000000000", "Республика Татарстан"),
    "ekb": ("6600000000000", "Свердловская область"),
    "nsk": ("5400000000000", "Новосибирская область"),
}

log = logging.getLogger("vacancy-parser")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Собирает вакансии с trudvsem.ru и строит отчёт в Excel.")
    parser.add_argument("-q", "--query", required=True, help="поисковый запрос, например \"python\"")
    parser.add_argument(
        "-r", "--region",
        help=f"регион: {', '.join(REGIONS)} или 13-значный код. По умолчанию вся Россия",
    )
    parser.add_argument("-p", "--pages", type=int, default=5, help="сколько страниц по 100 вакансий (по умолчанию 5)")
    parser.add_argument("--salary-from", type=int, help="только вакансии с зарплатой не ниже указанной, ₽")
    parser.add_argument("-o", "--output", type=Path, help="путь к .xlsx (по умолчанию генерируется из запроса)")
    args = parser.parse_args(argv)

    if args.pages < 1:
        parser.error("--pages должно быть не меньше 1")
    if args.region and args.region not in REGIONS and not re.fullmatch(r"\d{13}", args.region):
        parser.error(f"неизвестный регион «{args.region}». Используйте {', '.join(REGIONS)} или 13-значный код")
    return args


def default_output(query: str) -> Path:
    slug = re.sub(r"[^\w-]+", "_", query.lower()).strip("_") or "vacancies"
    return Path(f"vacancies_{slug}_{date.today():%Y-%m-%d}.xlsx")


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)

    region_code, region_name = REGIONS.get(args.region, (args.region, args.region or "Вся Россия"))
    output = args.output or default_output(args.query)

    try:
        raw = list(TrudvsemClient().search(args.query, region=region_code, max_pages=args.pages))
    except ApiError as exc:
        log.error("Ошибка API: %s", exc)
        return 1

    vacancies = prepare(raw, salary_min=args.salary_from)
    if not vacancies:
        log.warning("По запросу «%s» ничего не найдено, отчёт не создан", args.query)
        return 0

    try:
        build_report(vacancies, output, args.query, region_name)
    except PermissionError:
        log.error("Не удалось записать %s — возможно, файл открыт в Excel", output)
        return 1

    log.info("Готово: %d вакансий → %s", len(vacancies), output.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
