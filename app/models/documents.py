from app.database import Base
from sqlalchemy import DateTime, String, Integer, func, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from datetime import datetime

class CaseDocument(Base):
    __tablename__ = "case_documents"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # Reference ID of the document in the source (or legal reference number)
    reference_id: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )

    # Title of the document
    title: Mapped[str] = mapped_column(Text, nullable=False)

    # Type of the document (Judgment, Order, etc.)
    doc_type: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )

    jurisdiction: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )

    # Source of the document (Like Sindh Court, etc)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )

    citation: Mapped[str] = mapped_column(Text, nullable=True)

    year: Mapped[int] = mapped_column(Integer, nullable=True, index=True)

    # URL or path to the raw content of the document (location where the pdf or document is stored at the source)
    raw_content_uri: Mapped[str] = mapped_column(Text, nullable=True)

    # Legal status of the document (e.g., enacted, repealed, etc.)
    legal_status: Mapped[str] = mapped_column(String(255), nullable=True)
    
    # Content of the document (raw content of the document)
    contents: Mapped[str] = mapped_column(Text, nullable=True)

    # New fields for SHC Scraper (Standard Legal Fields)
    advocates: Mapped[str] = mapped_column(Text, nullable=True)
    case_type: Mapped[str] = mapped_column(Text, nullable=True)
    case_number: Mapped[str] = mapped_column(Text, nullable=True)
    bench: Mapped[str] = mapped_column(Text, nullable=True)
    parties: Mapped[str] = mapped_column(Text, nullable=True)
    topic: Mapped[str] = mapped_column(Text, nullable=True)
    decision_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # Flexible metadata for source-specific fields (e.g., tag_line)
    extra_metadata: Mapped[dict] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )