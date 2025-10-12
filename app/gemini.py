import os
import json
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
from logger_config import get_logger
import re

load_dotenv()
logger = get_logger(__name__)

async def extract_fields_from_gemini(payload: dict, pdf_text: str) -> dict:
    """
    Uses Gemini 2.5 Flash to extract structured fields from the PDF content and payload.
    Returns a dict suitable for inserting into the Document table.
    """

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        logger.error("Missing GEMINI_API_KEY in environment variables.")
        raise EnvironmentError("Missing GEMINI_API_KEY")

    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""
    You are an intelligent legal document parser.

    Extract and return a **valid JSON** with the following fields:
    reference_id, title, doc_type, jurisdiction, court, authority_level,
    tags (list), citation, date (YYYY-MM-DD), and legal_status.

    Use the given payload and the first 5000 characters of the PDF content for context.

    Payload:
    {json.dumps(payload, indent=2)}

    PDF Content (first 5000 chars):
    {pdf_text[:5000]}
    """

    try:
        # Run the model asynchronously
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction="You are a legal document parser that returns clean JSON only."
                ),
            )
        )

        text = response.text.strip()
        logger.debug(f"Raw Gemini response: {text[:200]}...")
        
        cleaned = re.sub(r"```(?:json)?|```", "", text).strip()

        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if not json_match:
            raise ValueError(f"No JSON object found in response:\n{cleaned}")

        json_str = json_match.group(0)

        # Parse the cleaned JSON
        extracted = json.loads(json_str)

        if not isinstance(extracted, dict):
            raise ValueError("Gemini response JSON is not an object")

        logger.info("Successfully extracted structured fields from Gemini.")
        return extracted

    except json.JSONDecodeError:
        logger.error("Gemini response is not valid JSON.")
        raise ValueError(f"Invalid Gemini response:\n{text}")

    except Exception as e:
        logger.exception(f"Unexpected error in extract_fields_from_gemini: {e}")
        raise
