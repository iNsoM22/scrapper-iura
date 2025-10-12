from typing import Optional
from app.models.documents import Document
from app.database import Base
from sqlalchemy.types import Integer, String, Text, DateTime
from sqlalchemy import ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))

    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    char_start: Mapped[int] = mapped_column(Integer, nullable=False)

    char_end: Mapped[int] = mapped_column(Integer, nullable=False)

    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)

    embedding_model: Mapped[Optional[str]] = mapped_column(String(100))

    embedding_version: Mapped[Optional[str]] = mapped_column(String(20))

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    ################
    # Relationships
    ################

    original_document: Mapped["Document"] = relationship(
        "Document", back_populates="chunks"
    )

    chunk_metadata: Mapped[Optional["MetadataChunk"]] = relationship(
        "MetadataChunk", back_populates="chunk", uselist=False
    )

    ################
    # Constraints
    ################

    __table_args__ = (
        UniqueConstraint('document_id', 'id', name='uix_document_id'),
    )
