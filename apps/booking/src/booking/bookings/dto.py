from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _clean(value: str) -> str:
    return " ".join(value.split())


class HoldDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    start: str
    timezone: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(max_length=200)
    company: str = Field(min_length=2, max_length=120)
    company_type: str = Field(alias="companyType", max_length=60)
    goal: str = Field(min_length=10, max_length=4000)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("name", "company")
    @classmethod
    def _tidy(cls, v: str) -> str:
        return _clean(v)


class VerifyDto(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class RescheduleDto(BaseModel):
    start: str
