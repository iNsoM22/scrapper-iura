from app.database import Base
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.chunks import Chunk


class MetadataChunk(Base):
    __tablename__ = "metadata_chunks"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True
    )

    doc_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    jurisdiction: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )

    citation: Mapped[str] = mapped_column(String(255), nullable=False)

    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    court: Mapped[str] = mapped_column(String(150), nullable=False)

    authority_level: Mapped[str] = mapped_column(String(100), nullable=False)

    tags: Mapped[str] = mapped_column(String(500), nullable=True)

    ################
    # Relationships
    ################

    chunk: Mapped["Chunk"] = relationship("Chunk", back_populates="chunk_metadata")

    ################
    # Constraints
    ################

    __table_args__ = (UniqueConstraint('chunk_id', 'id', name='uix_chunk_id'),)
