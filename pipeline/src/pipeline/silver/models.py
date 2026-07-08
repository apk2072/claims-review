"""Pydantic models validating Bedrock tool-use structured output."""

from pydantic import BaseModel

DOCUMENT_TYPES = ("medical_claim", "other")

EXPECTED_CLAIM_FIELDS = (
    "patient_name",
    "member_id",
    "date_of_birth",
    "provider_name",
    "date_of_service",
    "diagnosis_code",
    "procedure_code",
    "claim_amount",
)


class ClassificationResult(BaseModel):
    document_type: str


class FieldExtraction(BaseModel):
    fields: dict[str, str]
    field_confidences: dict[str, float]
