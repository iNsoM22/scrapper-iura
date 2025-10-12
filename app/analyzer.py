from sqlalchemy import select, desc
import asyncio
import json
from app.database import get_session
from app.models import RawDocument, Document
from app.gemini import extract_fields_from_gemini
from app.logger_config import get_logger

logger = get_logger(__name__)

def process_raw_documents(metadata_id: int, inserted_record_count: int):
    """
    Processes a batch of RawDocuments by extracting structured data from their PDF content
    and storing the results in the Document table.
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

            async def process_all():
                tasks = []
                for raw_doc in raw_docs:
                    payload = json.loads(raw_doc.payload)
                    pdf_text = raw_doc.pdf_raw
                    tasks.append(extract_fields_from_gemini(payload, pdf_text))
                return await asyncio.gather(*tasks, return_exceptions=True)

            extracted_results = asyncio.run(process_all())

            for raw_doc, extracted in zip(raw_docs, extracted_results):
                if isinstance(extracted, Exception):
                    logger.error(f"Failed to extract for raw_doc id={raw_doc.id}: {extracted}")
                    continue

                try:
                    doc = Document(
                        reference_id=extracted.get("reference_id"),
                        title=extracted.get("title"),
                        doc_type=extracted.get("doc_type"),
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
                except Exception as e:
                    logger.exception(f"Failed to prepare Document for raw_doc id={raw_doc.id}")
                    session.rollback()

            session.commit()
            logger.info(f"Successfully stored {len(raw_docs)} documents.")

    except Exception:
        logger.exception("process_raw_documents failed")
