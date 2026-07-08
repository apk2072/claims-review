"""Generate synthetic claim document fixtures for pipeline testing.

Run directly to (re)produce all fixture images:

    uv run python pipeline/tests/fixtures/sample_claims/generate_fixtures.py

All identifiers are obviously fake (e.g. "Jane Test Doe", "TEST-000000") —
this project never processes real PHI, even for local testing.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFilter

OUTPUT_DIR = pathlib.Path(__file__).parent

CLAIM_FIELDS = [
    ("Patient Name", "Jane Test Doe"),
    ("Member ID", "TEST-000000"),
    ("Date of Birth", "01/01/1980"),
    ("Provider Name", "Test Clinic Synthetic Health"),
    ("Date of Service", "06/15/2026"),
    ("Diagnosis Code", "Z00.00"),
    ("Procedure Code", "99213"),
    ("Claim Amount", "$125.00"),
]

INCOMPLETE_CLAIM_FIELDS = [
    ("Patient Name", "Jane Test Doe"),
    ("Member ID", "TEST-000001"),
    ("Date of Birth", ""),
    ("Provider Name", "Test Clinic Synthetic Health"),
    ("Date of Service", ""),
    ("Diagnosis Code", "Z00.00"),
    ("Procedure Code", ""),
    ("Claim Amount", "$89.50"),
]


def _render_form(title: str, fields: list[tuple[str, str]]) -> Image.Image:
    img = Image.new("RGB", (900, 600), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((40, 30), title, fill="black")
    draw.line((40, 60, 860, 60), fill="black")

    y = 100
    for label, value in fields:
        draw.text((40, y), f"{label}:", fill="black")
        draw.text((300, y), value if value else "(blank)", fill="black")
        y += 50

    return img


def generate_clean_high_confidence() -> None:
    img = _render_form("SYNTHETIC MEDICAL CLAIM FORM", CLAIM_FIELDS)
    img.save(OUTPUT_DIR / "clean_high_confidence.png")


def generate_blurry_low_confidence() -> None:
    img = _render_form("SYNTHETIC MEDICAL CLAIM FORM", CLAIM_FIELDS)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=4))
    blurred.save(OUTPUT_DIR / "blurry_low_confidence.png")


def generate_missing_fields() -> None:
    img = _render_form("SYNTHETIC MEDICAL CLAIM FORM", INCOMPLETE_CLAIM_FIELDS)
    img.save(OUTPUT_DIR / "missing_fields.png")


def generate_wrong_document_type() -> None:
    receipt_fields = [
        ("Store", "Synthetic Grocery Co."),
        ("Item", "Bread - $3.50"),
        ("Item", "Milk - $2.75"),
        ("Item", "Eggs - $4.25"),
        ("Total", "$10.50"),
    ]
    img = _render_form("GROCERY RECEIPT (NOT A CLAIM)", receipt_fields)
    img.save(OUTPUT_DIR / "wrong_document_type.png")


def main() -> None:
    generate_clean_high_confidence()
    generate_blurry_low_confidence()
    generate_missing_fields()
    generate_wrong_document_type()
    print(f"Generated 4 fixtures in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
