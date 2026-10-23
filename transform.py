"""Очистка и нормализация сырых вакансий из API."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from statistics import median


@dataclass
class Vacancy:
    id: str
    title: str
    company: str
    region: str
    salary_from: int | None
    salary_to: int | None
    experience_years: int | None
    schedule: str
    skills: list[str]
    published: date | None
    url: str

    @property
    def salary_estimate(self) -> float | None:
        """Одно число для статистики: середина вилки или та граница, что указана."""
        bounds = [s for s in (self.salary_from, self.salary_to) if s]
        return sum(bounds) / len(bounds) if bounds else None


def _salary(value) -> int | None:
    # API пишет 0, когда граница вилки не указана
    return int(value) if isinstance(value, (int, float)) and value > 0 else None


def _clean_text(value) -> str:
    if not isinstance(value, str):
        return ""
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip().strip('"«»').strip()


def _parse_date(value) -> date | None:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _experience(raw: dict) -> int | None:
    value = (raw.get("requirement") or {}).get("experience")
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _skills(raw: dict) -> list[str]:
    seen: dict[str, str] = {}
    for skill in raw.get("skills") or []:
        skill = _clean_text(skill)
        if skill:
            seen.setdefault(skill.lower(), skill)
    return list(seen.values())


def normalize(raw: dict) -> Vacancy:
    salary_from = _salary(raw.get("salary_min"))
    salary_to = _salary(raw.get("salary_max"))
    if salary_from and salary_to and salary_from > salary_to:
        salary_from, salary_to = salary_to, salary_from

    return Vacancy(
        id=raw["id"],
        title=_clean_text(raw.get("job-name")),
        company=_clean_text((raw.get("company") or {}).get("name")) or "Не указана",
        region=_clean_text((raw.get("region") or {}).get("name")),
        salary_from=salary_from,
        salary_to=salary_to,
        experience_years=_experience(raw),
        schedule=_clean_text(raw.get("schedule")),
        skills=_skills(raw),
        published=_parse_date(raw.get("creation-date")),
        url=raw.get("vac_url", ""),
    )


def prepare(raw_vacancies, salary_min: int | None = None) -> list[Vacancy]:
    """Нормализует, убирает дубликаты по id и применяет фильтр по зарплате."""
    result: dict[str, Vacancy] = {}
    for raw in raw_vacancies:
        vacancy = normalize(raw)
        if salary_min is not None:
            top = vacancy.salary_to or vacancy.salary_from
            if top is None or top < salary_min:
                continue
        result.setdefault(vacancy.id, vacancy)
    return sorted(result.values(), key=lambda v: v.published or date.min, reverse=True)


def experience_label(years: int | None) -> str:
    if years is None:
        return "Не указан"
    if years == 0:
        return "Без опыта"
    if years < 3:
        return "1–2 года"
    if years < 6:
        return "3–5 лет"
    return "6+ лет"


EXPERIENCE_ORDER = ["Без опыта", "1–2 года", "3–5 лет", "6+ лет", "Не указан"]


def salary_stats(vacancies: list[Vacancy]) -> dict:
    estimates = [v.salary_estimate for v in vacancies if v.salary_estimate]
    return {
        "count": len(estimates),
        "median": median(estimates) if estimates else None,
        "mean": sum(estimates) / len(estimates) if estimates else None,
    }
