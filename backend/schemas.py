from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StructuredFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str | None = Field(default=None, max_length=80)
    category: str = Field(min_length=1, max_length=100)
    claim: str = Field(min_length=1, max_length=2000)
    evidence: str = Field(min_length=1, max_length=4000)
    page_number: int = Field(ge=1)
    block_number: int = Field(ge=1)
    status: Literal["verified", "unverified", "issue"] = "unverified"


class MissingOrUnclear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
    question: str = Field(min_length=1, max_length=1000)


class StructuredFactsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_type: str | None = Field(default=None, max_length=200)
    project_type_evidence: str | None = Field(default=None, max_length=4000)
    project_type_page_number: int | None = Field(default=None, ge=1)
    project_type_block_number: int | None = Field(default=None, ge=1)
    facts: list[StructuredFact] = Field(default_factory=list, max_length=100)
    missing_or_unclear: list[MissingOrUnclear] = Field(default_factory=list, max_length=500)


class SectionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_name: str = Field(min_length=1, max_length=100)
    verified_fact_ids: list[str] = Field(default_factory=list, max_length=100)
    word_range: tuple[int, int]

    @field_validator("word_range")
    @classmethod
    def valid_word_range(cls, value: tuple[int, int]) -> tuple[int, int]:
        minimum, maximum = value
        if minimum < 20 or maximum > 2000 or minimum > maximum:
            raise ValueError("word range must be between 20 and 2000 words")
        return value


class SectionPlanList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[SectionPlan] = Field(max_length=50)
