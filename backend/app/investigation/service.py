"""Validate the entire report and references before it becomes visible."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.investigation.provider import ProviderFailure


class Claim(BaseModel):
    model_config = ConfigDict(extra='forbid')
    statement: str = Field(min_length=8, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)


class Hypothesis(Claim):
    confidence: Literal['low', 'medium', 'high']
    uncertainty: str = Field(min_length=8, max_length=500)


class Recommendation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: str = Field(min_length=8, max_length=500)
    reason: str = Field(min_length=8, max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=5)
    requires_approval: bool


class Report(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=8, max_length=800)
    summary_evidence_ids: list[str] = Field(min_length=1, max_length=5)
    observations: list[Claim] = Field(min_length=1, max_length=10)
    hypotheses: list[Hypothesis] = Field(max_length=5)
    recommendations: list[Recommendation] = Field(max_length=6)
    gaps: list[str] = Field(max_length=12)

    @model_validator(mode='after')
    def bounded_gaps(self):
        if any(len(item) > 500 for item in self.gaps):
            raise ValueError('Gap too long')
        return self


def validate_report(data: dict, evidence: list[dict], known_gaps: list[str]) -> dict:
    try:
        report = Report.model_validate(data)
    except (ValidationError, TypeError, ValueError):
        raise ProviderFailure('PROVIDER_MALFORMED') from None
    allowed = {item['id'] for item in evidence}
    references = [report.summary_evidence_ids]
    references += [claim.evidence_ids for claim in report.observations]
    references += [claim.evidence_ids for claim in report.hypotheses]
    references += [claim.evidence_ids for claim in report.recommendations]
    if any(any(identifier not in allowed for identifier in group) for group in references):
        raise ProviderFailure('FABRICATED_CITATION')
    # Changes to production systems are outside Stage 4; a report cannot propose execution.
    approved = re.compile(r'^(inspect|review|compare|check|verify|observe|measure)\b', re.I)
    writes = re.compile(r'\b(restart|reboot|deploy|rollback|roll back|delete|rotate|write|edit|change|modify|increase|decrease|scale|flush|drain|kill|stop|start)\b', re.I)
    if any(item.requires_approval or not approved.search(item.action) or writes.search(item.action)
           for item in report.recommendations):
        raise ProviderFailure('UNSAFE_RECOMMENDATION')
    report.gaps = list(dict.fromkeys([*report.gaps, *known_gaps]))[:12]
    return report.model_dump()
