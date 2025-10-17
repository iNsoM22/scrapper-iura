import os
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from logger_config import get_logger
import re
from datetime import datetime

load_dotenv()
logger = get_logger(__name__)

def extract_fields_from_gemini(payload: dict, pdf_text: str, max_retries: int = 2) -> dict:
    """
    Uses Gemini 2.5 Flash to extract structured fields from the PDF content and payload.
    Returns a fully normalized dict ready for SQLAlchemy insertion. Synchronous version.
    """

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise EnvironmentError("Missing GEMINI_API_KEY in environment variables.")

    client = genai.Client(api_key=GEMINI_API_KEY)

    # Define schema fields expected
    required_fields = [
        "reference_id", "title", "doc_type", "jurisdiction",
        "court", "authority_level", "citation", "legal_status"
    ]

    optional_fields = ["tags", "date"]

    # Build prompt
    base_prompt = f"""
    You are a professional AI trained to extract structured metadata from legal documents.

    **Return valid JSON only** (no markdown, no explanations) with these fields:
    reference_id, title, doc_type, jurisdiction, court, authority_level,
    tags (comma-separated string), citation, date (YYYY-MM-DD), legal_status.

    If any field is missing, make the best inference. Always ensure 'citation' and 'reference_id' are strings.

    Payload:
    {json.dumps(payload, indent=2)}

    PDF Content (first 5000 chars):
    {pdf_text[:5000]}
    """

    def _parse_response(text: str) -> dict:
        cleaned = re.sub(r"```(?:json)?|```", "", text).strip()
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if not json_match:
            raise ValueError(f"No JSON object found in response:\n{text[:300]}...")
        extracted = json.loads(json_match.group(0))
        if not isinstance(extracted, dict):
            raise ValueError("Gemini returned a non-dictionary JSON structure.")
        return extracted

    def _call_gemini(prompt: str):
        return client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a strict JSON generator. "
                    "Do not include any explanation or markdown. "
                    "Return only valid JSON that matches the expected fields."
                )
            ),
        )

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Gemini extraction attempt {attempt}/{max_retries}")
            response = _call_gemini(base_prompt)
            text = response.text.strip()

            extracted = _parse_response(text)
            logger.debug(f"Gemini raw JSON: {json.dumps(extracted, indent=2)[:500]}...")

            # --- Normalize fields for DB ---
            # Convert lists → comma strings
            for key in ("tags", "citation"):
                val = extracted.get(key)
                if isinstance(val, list):
                    extracted[key] = ", ".join([str(v).strip() for v in val if v])
                elif isinstance(val, (int, float)):
                    extracted[key] = str(val)
                elif val is None:
                    extracted[key] = ""

            # Clean up and title-case text fields
            text_fields = ["title", "doc_type", "jurisdiction", "court", "authority_level", "legal_status"]
            for key in text_fields:
                val = extracted.get(key)
                if isinstance(val, str):
                    extracted[key] = re.sub(r"\s+", " ", val).strip().title()

            # Validate and normalize date
            date_val = extracted.get("date")
            if date_val:
                try:
                    # Try to extract YYYY-MM-DD or any common format
                    dt = datetime.strptime(date_val[:10], "%Y-%m-%d")
                    extracted["date"] = dt.strftime("%Y-%m-%d")
                except Exception:
                    extracted["date"] = None
            else:
                extracted["date"] = None

            # Ensure all required fields are present
            for field in required_fields:
                if field not in extracted or not extracted[field]:
                    logger.warning(f"Missing or empty field: {field}")
                    extracted[field] = "Unknown"

            # Fill optional if missing
            for field in optional_fields:
                extracted.setdefault(field, "")

            logger.info("Successfully extracted and normalized structured fields.")
            return extracted

        except Exception as e:
            logger.warning(f"Gemini extraction failed (attempt {attempt}): {e}")
            if attempt == max_retries:
                logger.error("Gemini extraction failed after all retries.")
                raise
            time.sleep(2 * attempt)

