import json
import re
from app.database import get_supabase
from app.gemini import extract_fields_from_gemini
from app.logger_config import get_logger

logger = get_logger(__name__)


def _sanitize_for_db(text: str) -> str:
    """Remove NUL and other control characters that break PostgreSQL."""
    if not text:
        return text
    # Remove NUL (0x00) and other problematic control characters
    # Keep tab (0x09), newline (0x0A), and carriage return (0x0D)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)

def process_raw_documents(metadata_id: int, inserted_record_count: int):
    """
    Processes RawDocuments and stores structured data in the Document table.
    Avoids duplicate reference_id/title/doc_type and handles errors per record safely.
    """
    supabase = get_supabase()

    try:
        # Fetch raw documents ordered by created_at descending
        result = supabase.table("raw_documents").select("*").eq("metadata_id", metadata_id).order("created_at", desc=True).limit(inserted_record_count).execute()
        
        raw_docs = result.data if result.data else []

        if not raw_docs:
            logger.info(f"No RawDocuments found for metadata_id={metadata_id}")
            return

        logger.info(f"Processing {len(raw_docs)} RawDocuments for metadata_id={metadata_id}")

        documents_to_insert = []
        processed_refs = set()  # Track reference_ids to avoid duplicates in this batch

        for raw_doc in raw_docs:
            try:
                # Extract fields
                payload = json.loads(raw_doc["payload"])
                pdf_text = raw_doc["pdf_raw"]
                extracted = extract_fields_from_gemini(payload, pdf_text)
            except Exception as e:
                logger.error(f"Failed to extract for raw_doc id={raw_doc['id']}: {e}")
                continue

            try:
                ref_id = (extracted.get("reference_id") or "Unknown").strip()
                title = (extracted.get("title") or "").strip()
                doc_type = (extracted.get("doc_type") or "").strip()

                # Check duplicates in DB
                existing_result = supabase.table("documents").select("id").eq("reference_id", ref_id).execute()

                if existing_result.data:
                    logger.info(
                        f"Skipping raw_doc id={raw_doc['id']}: duplicate reference_id '{ref_id}' already in DB."
                    )
                    continue

                # Check duplicates in current batch
                if ref_id in processed_refs:
                    logger.info(
                        f"Skipping raw_doc id={raw_doc['id']}: duplicate reference_id '{ref_id}' in current batch."
                    )
                    continue

                # Create Document record
                doc = {
                    "reference_id": _sanitize_for_db(ref_id),
                    "title": _sanitize_for_db(title),
                    "doc_type": _sanitize_for_db(doc_type),
                    "jurisdiction": _sanitize_for_db(extracted.get("jurisdiction") or ""),
                    "court": _sanitize_for_db(extracted.get("court") or ""),
                    "authority_level": _sanitize_for_db(extracted.get("authority_level") or ""),
                    "tags": _sanitize_for_db(extracted.get("tags") or ""),
                    "citation": _sanitize_for_db(extracted.get("citation") or ""),
                    "year": int(str(extracted.get("date", "")).split("-")[0]) if extracted.get("date") else 0,
                    "raw_content_uri": _sanitize_for_db(raw_doc["pdf_uri"]),
                    "legal_status": _sanitize_for_db(extracted.get("legal_status") or ""),
                    "raw_content": _sanitize_for_db(raw_doc["pdf_raw"]),
                }

                documents_to_insert.append(doc)
                processed_refs.add(ref_id)
                logger.info(f"Prepared Document for raw_doc id={raw_doc['id']}")

            except Exception as e:
                logger.exception(f"Error preparing Document for raw_doc id={raw_doc['id']}")
                continue

        # Batch insert documents
        if documents_to_insert:
            try:
                insert_result = supabase.table("documents").insert(documents_to_insert).execute()
                logger.info(f"Successfully inserted {len(documents_to_insert)} documents.")
            except Exception as insert_error:
                logger.error(f"Failed to batch insert documents: {insert_error}")
                # Try inserting one by one
                for doc in documents_to_insert:
                    try:
                        supabase.table("documents").insert(doc).execute()
                        logger.info(f"Individually inserted document with reference_id={doc['reference_id']}")
                    except Exception as e:
                        logger.error(f"Failed to insert document with reference_id={doc['reference_id']}: {e}")

        logger.info(f"Completed processing {len(raw_docs)} documents.")

    except Exception:
        logger.exception("process_raw_documents failed")
