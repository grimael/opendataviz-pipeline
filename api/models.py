"""Pydantic response models for the OpenDataViz API."""

from pydantic import BaseModel


class IndicatorOut(BaseModel):
    code: str
    name: str
    category: str
    unit: str
    short_name: str


class CountryOut(BaseModel):
    iso3: str
    iso2: str
    name: str
    region: str
    income_level: str | None = None
    capital_city: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class DataPoint(BaseModel):
    country_iso3: str
    country_name: str
    year: int
    value: float | None
    is_imputed: bool
    imputation_method: str | None = None


class ProjectionPoint(BaseModel):
    country_iso3: str
    country_name: str
    year: int
    projected_value: float
    method: str
    confidence: float | None = None


class HealthStatus(BaseModel):
    status: str
    database: str
    total_facts: int
    total_imputed: int
    total_projections: int
    last_quality_score: float | None = None
    last_quality_run: str | None = None
