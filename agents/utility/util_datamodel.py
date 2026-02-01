import logging

from datetime import datetime, date
from typing import Any, Dict

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    inspect as sqlalchemy_inspect
)
from sqlalchemy.orm import Mapped, mapped_column
from .util_database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        "CreatedAt",
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        "UpdatedAt",
        DateTime,
        nullable=True,
        onupdate=datetime.utcnow,
    )


class IdMixin:
    id: Mapped[int] = mapped_column(
        "Id",
        Integer,
        primary_key=True,
        autoincrement=True,
    )


class BaseModel(Base, IdMixin, TimestampMixin):
    __abstract__ = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dict using SQLAlchemy mapper for proper attribute access."""
        from datetime import datetime, date
        mapper = sqlalchemy_inspect(self.__class__)
        d: Dict[str, Any] = {}
        for attr in mapper.attrs:
            if not hasattr(attr, 'columns') or len(attr.columns) == 0:
                continue
            sql_name = attr.columns[0].name
            python_attr = attr.key
            value = getattr(self, python_attr)

            if isinstance(value, (datetime, date)):
                value = value.isoformat()

            d[sql_name] = value
        return d


class LLMTokenUsage(BaseModel):
    """Track LLM token usage for analytics and cost reporting."""
    __tablename__ = "LLMTokenUsage"

    __create_sql__ = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LLMTokenUsage' AND xtype='U')
    CREATE TABLE LLMTokenUsage (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        AgentType NVARCHAR(50) NOT NULL,
        AgentOperation NVARCHAR(50) NULL,
        ModelName NVARCHAR(50) NOT NULL,
        InputTokens INT NOT NULL,
        OutputTokens INT NOT NULL,
        InferenceRounds INT NULL DEFAULT 0,
        Description NVARCHAR(500) NULL,
        StartedAt DATETIME NOT NULL,
        CompletedAt DATETIME NULL,
        CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
        UpdatedAt DATETIME NULL
    );

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_llm_agent_type' AND object_id = OBJECT_ID('LLMTokenUsage'))
    CREATE INDEX idx_llm_agent_type ON LLMTokenUsage(AgentType);

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_llm_created_at' AND object_id = OBJECT_ID('LLMTokenUsage'))
    CREATE INDEX idx_llm_created_at ON LLMTokenUsage(CreatedAt);
    """

    # Agent context
    agent_type: Mapped[str] = mapped_column(
        "AgentType",
        String(50),
        nullable=False
    )
    agent_operation: Mapped[str | None] = mapped_column(
        "AgentOperation",
        String(50),
        nullable=True
    )

    # Token metrics
    model_name: Mapped[str] = mapped_column(
        "ModelName",
        String(50),
        nullable=False
    )
    input_tokens: Mapped[int] = mapped_column(
        "InputTokens",
        Integer,
        nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        "OutputTokens",
        Integer,
        nullable=False
    )
    inference_rounds: Mapped[int | None] = mapped_column(
        "InferenceRounds",
        Integer,
        nullable=True,
        default=0
    )

    # Description
    description: Mapped[str | None] = mapped_column(
        "Description",
        String(500),
        nullable=True
    )

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        "StartedAt",
        DateTime,
        nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        "CompletedAt",
        DateTime,
        nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<LLMTokenUsage agent={self.agent_type!r} "
            f"model={self.model_name!r} tokens={self.input_tokens + self.output_tokens}>"
        )
