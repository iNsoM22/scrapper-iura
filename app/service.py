from sqlalchemy import String, select
from sqlalchemy.exc import IntegrityError
from app.database import get_session
from app.models import MetadataRaw, RawDocument
from app.pdf_collector import fetch_pdf_text
from app.logger_config import get_logger
import asyncio
import json
from app.analyzer import process_raw_documents

logger = get_logger(__name__)


def store_raw_metadata(uri: str, delimiter: str, structure: list[str]) -> int:
    """
    Connects to the database and stores metadata in the MetadataRaw table.
    Ensures no duplicate record exists with the same (uri, delimiter, structure).
    Returns the ID of the stored or existing record.
    """
    with get_session() as session:
        try:
            # Check if record already exists
            existing = session.scalar(
                select(MetadataRaw)
                .where(
                    MetadataRaw.fetch_uri == uri,
                    MetadataRaw.delimiter == delimiter,
                    MetadataRaw.structure.cast(String) == json.dumps(structure)
                )
            )

            if existing:
                logger.info(
                    f"Metadata already exists for URI={uri}, delimiter={delimiter}, structure={structure}"
                )
                return existing.id

            # Otherwise, create a new record
            meta = MetadataRaw(
                fetch_uri=uri,
                delimiter=delimiter,
                structure=structure,
            )
            session.add(meta)
            session.commit()
            session.refresh(meta)

            logger.info(
                f"Stored new metadata entry (ID={meta.id}) for URI={uri}, delimiter={delimiter}"
            )
            return meta.id

        except IntegrityError:
            session.rollback()
            existing = session.scalar(
                select(MetadataRaw)
                .where(
                    MetadataRaw.fetch_uri == uri,
                    MetadataRaw.delimiter == delimiter,
                    MetadataRaw.structure == structure,
                )
            )
            if existing:
                logger.warning(
                    f"Duplicate metadata found, returning existing ID={existing.id} "
                    f"for URI={uri}, delimiter={delimiter}"
                )
                return existing.id
            else:
                logger.error(f"IntegrityError occurred, but no existing record found for URI={uri}")
                return None

        except Exception as e:
            session.rollback()
            logger.exception(f"Unexpected error in store_raw_metadata for URI={uri}: {e}")
            raise




def store_batch_records(metadata_id: int, data: list[dict], pdf_link_key: str):
    """
    Stores a batch of records in the RawDocument table.
    - Uses metadata_id as a foreign key.
    - Fetches and extracts text from the PDF using pdf_collector.
    - Stores payload and extracted PDF text.
    """

    async def process_record(record):
        pdf_url = record.get(pdf_link_key)
        if not pdf_url:
            raise ValueError(f"Missing PDF URL in record (key='{pdf_link_key}')")

        logger.info(f"Fetching PDF for record: {pdf_url}")
        pdf_info = await fetch_pdf_text(pdf_url)
        logger.info(f"Extracted {pdf_info.pages} pages from PDF: {pdf_url}")

        return {
            "payload": json.dumps(record),
            "pdf_uri": pdf_url,
            "pdf_raw": pdf_info.text,
        }

    async def process_all():
        results = []
        for record in data:
            try:
                result = await process_record(record)
                results.append(result)
            except Exception as e:
                logger.warning(f"Skipping record due to PDF error: {e}")
        return results

    try:
        processed = asyncio.run(process_all())

        with get_session() as session:
            for entry in processed:
                doc = RawDocument(
                    metadata_id=metadata_id,
                    payload=entry["payload"],
                    pdf_uri=entry["pdf_uri"],
                    pdf_raw=entry["pdf_raw"],
                )
                session.add(doc)

            session.commit()
            logger.info(
                f"Stored {len(processed)} raw documents successfully for metadata_id={metadata_id}"
            )
        process_raw_documents(metadata_id, len(processed))
            
        

    except Exception as e:
        logger.exception(f"Failed to store batch records for metadata_id={metadata_id}: {e}")