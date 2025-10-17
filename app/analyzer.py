from sqlalchemy import select, desc
import json
from app.database import get_session
from app.models import RawDocument, Document
from app.gemini import extract_fields_from_gemini
from app.logger_config import get_logger

logger = get_logger(__name__)

def process_raw_documents(metadata_id: int, inserted_record_count: int):
    """
    Processes RawDocuments and stores structured data in the Document table.
    Avoids duplicate reference_id/title/doc_type and handles errors per record safely.
    """

    try:
        with get_session() as session:
            raw_docs = (
                session.scalars(
                    select(RawDocument)
                    .where(RawDocument.metadata_id == metadata_id)
                    .order_by(desc(RawDocument.created_at))
                    .limit(inserted_record_count)
                )
                .all()
            )

            if not raw_docs:
                logger.info(f"No RawDocuments found for metadata_id={metadata_id}")
                return

            logger.info(f"Processing {len(raw_docs)} RawDocuments for metadata_id={metadata_id}")

            for raw_doc in raw_docs:
                try:
                    # Extract fields
                    payload = json.loads(raw_doc.payload)
                    pdf_text = raw_doc.pdf_raw
                    extracted = extract_fields_from_gemini(payload, pdf_text)
                except Exception as e:
                    logger.error(f"Failed to extract for raw_doc id={raw_doc.id}: {e}")
                    continue

                try:
                    ref_id = (extracted.get("reference_id") or "Unknown").strip()
                    title = (extracted.get("title") or "").strip()
                    doc_type = (extracted.get("doc_type") or "").strip()

                    # Check duplicates in DB
                    existing = session.scalar(
                        select(Document).where(Document.reference_id == ref_id)
                    )

                    # Also check duplicates in pending session
                    in_session_duplicate = any(
                        isinstance(obj, Document)
                        and obj.reference_id == ref_id
                        for obj in session.new
                    )

                    if existing or in_session_duplicate:
                        logger.info(
                            f"Skipping raw_doc id={raw_doc.id}: duplicate reference_id '{ref_id}'."
                        )
                        continue

                    # Create Document
                    doc = Document(
                        reference_id=ref_id,
                        title=title,
                        doc_type=doc_type,
                        jurisdiction=extracted.get("jurisdiction"),
                        court=extracted.get("court"),
                        authority_level=extracted.get("authority_level"),
                        tags=extracted.get("tags"),
                        citation=extracted.get("citation"),
                        year=int(str(extracted.get("date", "")).split("-")[0]) if extracted.get("date") else 0,
                        raw_content_uri=raw_doc.pdf_uri,
                        legal_status=extracted.get("legal_status"),
                        raw_content=raw_doc.pdf_raw,
                    )

                    session.add(doc)
                    try:
                        session.flush()
                        logger.info(f"Inserted Document for raw_doc id={raw_doc.id}")
                    except Exception as insert_error:
                        session.rollback()
                        logger.error(
                            f"Failed to insert Document for raw_doc id={raw_doc.id}: {insert_error}"
                        )
                        continue

                except Exception as e:
                    logger.exception(f"Error preparing Document for raw_doc id={raw_doc.id}")
                    session.rollback()
                    continue

            session.commit()
            logger.info(f"Completed processing {len(raw_docs)} documents successfully.")

    except Exception:
        logger.exception("process_raw_documents failed")
