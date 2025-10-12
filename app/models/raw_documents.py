from app.database import Base
from sqlalchemy import DateTime, String, Integer, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime


class RawDocument(Base):
    __tablename__ = "raw_documents"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )

    # Foreign key from metadata_raw
    metadata_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("metadata_raw.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    payload: Mapped[str] = mapped_column(Text, nullable=False)

    pdf_uri: Mapped[str] = mapped_column(String(1000), nullable=False)

    pdf_raw: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    
    ################
    # Relationships
    ################
    
    raw_metadata: Mapped["MetadataRaw"] = relationship(
        "MetadataRaw",
        back_populates="raw_documents"
    )

