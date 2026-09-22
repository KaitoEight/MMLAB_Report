"""Strict Pydantic v2 schemas. Independent fields retain independent errors."""
from __future__ import annotations

import re
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from .members import fold, resolve_members
from .normalization import normalize_role, normalize_ranking

REPORT_TYPES = {"paper": "Paper", "de tai": "Đề tài", "ncs": "NCS",
                "seminar": "Seminar", "giai thuong": "Giải thưởng"}
PAPER_RANKINGS = {"A*", "A", "B", "C", "C-Unranked", "Q1", "Q2", "Q3", "Q4", "Q-Unranked"}
# The request's ellipsis is NOT a wildcard. Extend explicitly in policy changes.
PROJECT_RANKINGS = {fold(v): v for v in ("C", "CS1", "B", "A", "NAFOSTED", "Bộ", "ĐHQG")}
LABELS = {"report_type": "Type of Report", "title": "Title of Work", "authors": "All authors",
          "venue": "Venue", "role": "Role", "index": "Index", "ranking": "Ranking",
          "subject": "Subject", "done": "Đã", "planned": "Sẽ"}


def enum_key(value: str) -> str:
    return re.sub(r"[\s\-‐‑–—]+", " ", fold(value)).strip()


def report_type(value):
    return REPORT_TYPES.get(enum_key(value), value.strip()) if isinstance(value, str) else value


class StrictModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", str_strip_whitespace=True,
                              validate_default=True)

    @field_validator("*", mode="before")
    @classmethod
    def strip_strings(cls, value):
        return value.strip() if isinstance(value, str) else value


class WorkReport(StrictModel):
    report_type: Literal["Paper", "Đề tài"]
    title: str = Field(min_length=5)
    authors: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    role: Literal["First author", "Co-author"]
    index: str = ""
    ranking: str = Field(min_length=1)
    credited_members: list[dict] = Field(default_factory=list, exclude=True)

    @field_validator("report_type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        return report_type(value)

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        if not isinstance(value, str):
            return value
        return normalize_role(value)

    @field_validator("index")
    @classmethod
    def validate_index(cls, value, info: ValidationInfo):
        kind = info.data.get("report_type")
        if kind == "Đề tài" and value in ("", "-"):
            return value
        if kind not in ("Paper", "Đề tài"):
            return value  # No guessed conditional rules for an unknown report type.
        if not value:
            raise PydanticCustomError("required_empty", "Index là bắt buộc đối với Paper")
        tokens = re.split(r"\s*(?:[,;/&+]|\band\b|\bvà\b)\s*", value, flags=re.I)
        canonical = {"scopus": "Scopus", "isi": "ISI"}
        if not tokens or any(t.casefold().strip() not in canonical for t in tokens):
            raise ValueError("Index phải là Scopus, ISI hoặc cả hai; đề tài được phép trống/-")
        return "; ".join(dict.fromkeys(canonical[t.casefold().strip()] for t in tokens))

    @field_validator("ranking")
    @classmethod
    def validate_ranking(cls, value, info: ValidationInfo):
        kind = info.data.get("report_type")
        key = enum_key(normalize_ranking(value) if kind == "Paper" else value)
        allowed = ({enum_key(v): v for v in PAPER_RANKINGS} if kind == "Paper"
                   else PROJECT_RANKINGS if kind == "Đề tài" else None)
        if allowed is None:
            return value
        if key not in allowed:
            raise ValueError("Ranking Paper phải thuộc A*, A, B, C, C-Unranked, Q1–Q4, Q-Unranked"
                             if kind == "Paper" else "Cấp đề tài chưa nằm trong whitelist cấu hình")
        return allowed[key]

    @model_validator(mode="after")
    def derive_members(self):
        # No validation errors here: field errors above must accumulate, not short circuit.
        self.credited_members = resolve_members(self.authors)
        return self


class MilestoneReport(StrictModel):
    report_type: Literal["NCS", "Seminar", "Giải thưởng"]
    title: str = Field(min_length=1)

    @field_validator("report_type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        return report_type(value)


class DoneTask(StrictModel):
    date: str
    content: str

    @field_validator("date")
    @classmethod
    def normalize_date(cls, value, info: ValidationInfo):
        # Best-effort display normalization only; dates never invalidate a task.
        match = re.fullmatch(r"(\d{2})/(\d{2})(?:/(\d{4}))?", value)
        if not match:
            return value
        day, month = int(match[1]), int(match[2])
        # Use the report year when available; keep unparseable input as written.
        year = int(match[3]) if match[3] else (info.context or {}).get("year", 2000)
        try:
            parsed = date(year, month, day)
        except ValueError:
            return value
        return parsed.isoformat() if match[3] or "year" in (info.context or {}) else value


class MonthlyReport(StrictModel):
    subject: str = ""
    done: list[DoneTask] | None = None
    planned: list[str] | None = None

