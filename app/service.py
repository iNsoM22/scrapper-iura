from app.database import get_supabase
from app.pdf_collector import fetch_pdf_text
from app.logger_config import get_logger
import json
import re
from app.analyzer import process_raw_documents

logger = get_logger(__name__)


def _sanitize_for_db(text: str) -> str:
    """Remove NUL and other control characters that break PostgreSQL."""
    if not text:
        return text
    # Remove NUL (0x00) and other problematic control characters
    # Keep tab (0x09), newline (0x0A), and carriage return (0x0D)
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)


def store_raw_metadata(uri: str, delimiter: str, structure: list[str]) -> int:
    """
    Connects to the database and stores metadata in the MetadataRaw table.
    Ensures no duplicate record exists with the same (uri, delimiter, structure).
    Returns the ID of the stored or existing record.
    """
    supabase = get_supabase()
    
    try:
        # Check if record already exists
        result = supabase.table("metadata_raw").select("id").eq("fetch_uri", uri).eq("delimiter", delimiter).execute()
        
        # Additional check for structure match (JSON comparison)
        if result.data:
            for record in result.data:
                # Fetch full record to compare structure
                full_record = supabase.table("metadata_raw").select("*").eq("fetch_uri", record["id"],
                                                                            ""
                                                                            ).execute()
                if full_record.data and full_record.data[0]["structure"] == structure:
                    logger.info(
                        f"Metadata already exists for URI={uri}, delimiter={delimiter}, structure={structure}"
                    )
                    return full_record.data[0]["id"]

        # Otherwise, create a new record
        new_meta = {
            "fetch_uri": uri,
            "delimiter": delimiter,
            "structure": structure,
        }
        
        insert_result = supabase.table("metadata_raw").insert(new_meta).execute()
        
        if insert_result.data:
            meta_id = insert_result.data[0]["id"]
            logger.info(
                f"Stored new metadata entry (ID={meta_id}) for URI={uri}, delimiter={delimiter}"
            )
            return meta_id
        else:
            logger.error(f"Failed to insert metadata for URI={uri}")
            return None

    except Exception as e:
        logger.exception(f"Unexpected error in store_raw_metadata for URI={uri}: {e}")
        # Try to fetch existing record in case of conflict
        try:
            result = supabase.table("metadata_raw").select("*").eq("fetch_uri", uri).eq("delimiter", delimiter).execute()
            if result.data:
                for record in result.data:
                    if record["structure"] == structure:
                        logger.warning(
                            f"Duplicate metadata found, returning existing ID={record['id']} "
                            f"for URI={uri}, delimiter={delimiter}"
                        )
                        return record["id"]
        except Exception:
            pass
        raise




def store_batch_records(metadata_id: int, data: list[dict], pdf_link_key: str):
    """
    Stores a batch of records in the RawDocument table.
    - Uses metadata_id as a foreign key.
    - Fetches and extracts text from the PDF using pdf_collector.
    - Stores payload and extracted PDF text.
    """
    supabase = get_supabase()

    try:
        processed = []
        for record in data:
            try:
                pdf_url = record.get(pdf_link_key)
                if not pdf_url:
                    raise ValueError(f"Missing PDF URL in record (key='{pdf_link_key}')")

                logger.info(f"Fetching PDF for record: {pdf_url}")
                pdf_info = fetch_pdf_text(pdf_url)
                logger.info(f"Extracted {pdf_info.pages} pages from PDF: {pdf_url}")

                processed.append({
                    "metadata_id": metadata_id,
                    "payload": _sanitize_for_db(json.dumps(record)),
                    "pdf_uri": _sanitize_for_db(pdf_url),
                    "pdf_raw": _sanitize_for_db(pdf_info.text),
                })
            except Exception as e:
                logger.warning(f"Skipping record due to PDF error: {e}")

        if processed:
            # Insert all processed records using Supabase
            insert_result = supabase.table("raw_documents").insert(processed).execute()
            
            logger.info(
                f"Stored {len(processed)} raw documents successfully for metadata_id={metadata_id}"
            )
            process_raw_documents(metadata_id, len(processed))
        else:
            logger.warning(f"No records to store for metadata_id={metadata_id}")

    except Exception as e:
        logger.exception(f"Failed to store batch records for metadata_id={metadata_id}: {e}")