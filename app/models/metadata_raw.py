from app.database import Base
from sqlalchemy import JSON, DateTime, String, Integer, func
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship


class MetadataRaw(Base):
    __tablename__ = "metadata_raw"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    
    fetch_uri: Mapped[str] = mapped_column(
        String(1000), nullable=False, unique=True, index=True
    )

    structure: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    
    delimiter: Mapped[str] = mapped_column(String(10), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    ################
    # Relationships
    ################
    raw_documents: Mapped[list["RawDocument"]] = relationship(
        "RawDocument",
        back_populates="raw_metadata",
        cascade="all, delete-orphan"
    )
