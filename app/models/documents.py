from app.database import Base
from sqlalchemy import DateTime, String, Integer, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chunks import Chunk


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    reference_id: Mapped[str] = mapped_column(
        Text, unique=True, nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)

    doc_type: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )

    jurisdiction: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )

    court: Mapped[str] = mapped_column(String(255), nullable=False)

    authority_level: Mapped[str] = mapped_column(String(255), nullable=False)

    tags: Mapped[str] = mapped_column(Text, nullable=True)

    citation: Mapped[str] = mapped_column(Text, nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    raw_content_uri: Mapped[str] = mapped_column(Text, nullable=False)

    legal_status: Mapped[str] = mapped_column(String(255), nullable=False)
    
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    ################
    # Relationships
    ################

    chunks: Mapped[list["Chunk"]] = relationship(
        "Chunk", back_populates="original_document", cascade="all, delete-orphan"
    )
