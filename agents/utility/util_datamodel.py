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


class AgentDefinition(BaseModel):
    """Central agent definition — single source of truth for agent name, description, and model."""
    __tablename__ = "AgentDefinition"

    __upsert_keys__ = ["name"]

    __create_sql__ = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='AgentDefinition' AND xtype='U')
    CREATE TABLE AgentDefinition (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        Name NVARCHAR(100) NOT NULL UNIQUE,
        Description NVARCHAR(500) NULL,
        Model NVARCHAR(100) NOT NULL,
        KnowledgeSource NVARCHAR(500) NULL,
        VectorStoreId NVARCHAR(100) NULL,
        FileManifest NVARCHAR(MAX) NULL,
        LastIndexedAt DATETIME NULL,
        IsActive BIT NOT NULL DEFAULT 1,
        CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
        UpdatedAt DATETIME
    );

    -- Migration: add knowledge columns if missing
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentDefinition' AND COLUMN_NAME='KnowledgeSource')
    ALTER TABLE AgentDefinition ADD KnowledgeSource NVARCHAR(500) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentDefinition' AND COLUMN_NAME='VectorStoreId')
    ALTER TABLE AgentDefinition ADD VectorStoreId NVARCHAR(100) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentDefinition' AND COLUMN_NAME='FileManifest')
    ALTER TABLE AgentDefinition ADD FileManifest NVARCHAR(MAX) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentDefinition' AND COLUMN_NAME='LastIndexedAt')
    ALTER TABLE AgentDefinition ADD LastIndexedAt DATETIME NULL;
    """

    name: Mapped[str] = mapped_column("Name", String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column("Description", String(500), nullable=True)
    model: Mapped[str] = mapped_column("Model", String(100), nullable=False)
    knowledge_source: Mapped[str | None] = mapped_column("KnowledgeSource", String(500), nullable=True)
    vector_store_id: Mapped[str | None] = mapped_column("VectorStoreId", String(100), nullable=True)
    file_manifest: Mapped[str | None] = mapped_column("FileManifest", String, nullable=True)
    last_indexed_at: Mapped[datetime | None] = mapped_column("LastIndexedAt", DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column("IsActive", Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"<AgentDefinition name={self.name!r} model={self.model!r}>"


class AgentPromptRegistry(BaseModel):
    """Registry mapping agents to their system prompt blobs.

    Supports both AgentId (FK to AgentDefinition) and AgentType (string name)
    for backward compatibility with the NUS repo.
    """
    __tablename__ = "AgentPromptRegistry"

    __upsert_keys__ = ["agent_id"]

    __create_sql__ = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='AgentPromptRegistry' AND xtype='U')
    CREATE TABLE AgentPromptRegistry (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        AgentType NVARCHAR(100) NULL,
        AgentId INT NULL,
        BlobPath NVARCHAR(500) NOT NULL,
        Description NVARCHAR(500) NULL,
        IsActive BIT NOT NULL DEFAULT 1,
        CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
        UpdatedAt DATETIME
    );

    -- Migration: add AgentType if table exists with only AgentId
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentPromptRegistry' AND COLUMN_NAME='AgentId')
       AND NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentPromptRegistry' AND COLUMN_NAME='AgentType')
    ALTER TABLE AgentPromptRegistry ADD AgentType NVARCHAR(100) NULL;

    -- Migration: add AgentId if table exists with only AgentType
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentPromptRegistry' AND COLUMN_NAME='AgentType')
       AND NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentPromptRegistry' AND COLUMN_NAME='AgentId')
    ALTER TABLE AgentPromptRegistry ADD AgentId INT NULL;

    -- Migration: make AgentType nullable if it was NOT NULL
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentPromptRegistry' AND COLUMN_NAME='AgentType' AND IS_NULLABLE='NO')
    ALTER TABLE AgentPromptRegistry ALTER COLUMN AgentType NVARCHAR(100) NULL;

    -- Migration: drop UNIQUE constraint on AgentType if it exists
    IF EXISTS (SELECT 1 FROM sys.indexes WHERE name LIKE 'UQ%' AND object_id = OBJECT_ID('AgentPromptRegistry'))
    BEGIN
        DECLARE @constraintName1 NVARCHAR(200);
        SELECT @constraintName1 = name FROM sys.indexes WHERE object_id = OBJECT_ID('AgentPromptRegistry') AND is_unique = 1 AND name LIKE 'UQ%';
        IF @constraintName1 IS NOT NULL EXEC('ALTER TABLE AgentPromptRegistry DROP CONSTRAINT [' + @constraintName1 + ']');
    END
    """

    agent_type: Mapped[str | None] = mapped_column("AgentType", String(100), nullable=True)
    agent_id: Mapped[int | None] = mapped_column("AgentId", Integer, nullable=True)
    blob_path: Mapped[str] = mapped_column("BlobPath", String(500), nullable=False)
    description: Mapped[str | None] = mapped_column("Description", String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column("IsActive", Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"<AgentPromptRegistry agent_type={self.agent_type!r} agent_id={self.agent_id!r}>"


class AgentToolMapping(BaseModel):
    """Maps agents to their tool definitions in blob storage.

    Supports both AgentId (FK to AgentDefinition) and AgentType (string name)
    for backward compatibility with the NUS repo.
    """
    __tablename__ = "AgentToolMapping"

    __upsert_keys__ = ["agent_id", "tool_name"]

    __create_sql__ = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='AgentToolMapping' AND xtype='U')
    CREATE TABLE AgentToolMapping (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        AgentType NVARCHAR(100) NULL,
        AgentId INT NULL,
        ToolName NVARCHAR(100) NOT NULL,
        BlobPath NVARCHAR(500) NOT NULL,
        ExecutorName NVARCHAR(100) NOT NULL,
        IsActive BIT NOT NULL DEFAULT 1,
        CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
        UpdatedAt DATETIME,
        CONSTRAINT UQ_AgentToolMapping UNIQUE (AgentId, ToolName)
    );

    -- Migration: add AgentType if table exists with only AgentId
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentToolMapping' AND COLUMN_NAME='AgentId')
       AND NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentToolMapping' AND COLUMN_NAME='AgentType')
    ALTER TABLE AgentToolMapping ADD AgentType NVARCHAR(100) NULL;

    -- Migration: add AgentId if table exists with only AgentType
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentToolMapping' AND COLUMN_NAME='AgentType')
       AND NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentToolMapping' AND COLUMN_NAME='AgentId')
    ALTER TABLE AgentToolMapping ADD AgentId INT NULL;

    -- Migration: make AgentType nullable if it was NOT NULL
    IF EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='AgentToolMapping' AND COLUMN_NAME='AgentType' AND IS_NULLABLE='NO')
    ALTER TABLE AgentToolMapping ALTER COLUMN AgentType NVARCHAR(100) NULL;
    """

    agent_type: Mapped[str | None] = mapped_column("AgentType", String(100), nullable=True)
    agent_id: Mapped[int | None] = mapped_column("AgentId", Integer, nullable=True)
    tool_name: Mapped[str] = mapped_column("ToolName", String(100), nullable=False)
    blob_path: Mapped[str] = mapped_column("BlobPath", String(500), nullable=False)
    executor_name: Mapped[str] = mapped_column("ExecutorName", String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column("IsActive", Integer, nullable=False, default=1)

    def __repr__(self) -> str:
        return f"<AgentToolMapping agent_type={self.agent_type!r} agent_id={self.agent_id!r} tool={self.tool_name!r}>"


class LLMTokenUsage(BaseModel):
    """Track LLM token usage for analytics and cost reporting."""
    __tablename__ = "LLMTokenUsage"

    __create_sql__ = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='LLMTokenUsage' AND xtype='U')
    CREATE TABLE LLMTokenUsage (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        StudentConfigId INT NULL,
        StudentId NVARCHAR(50) NULL,
        AgentId INT NULL,
        AgentType NVARCHAR(50) NULL,
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

    -- Migration: add columns if missing (shared table across projects)
    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='LLMTokenUsage' AND COLUMN_NAME='StudentConfigId')
    ALTER TABLE LLMTokenUsage ADD StudentConfigId INT NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='LLMTokenUsage' AND COLUMN_NAME='StudentId')
    ALTER TABLE LLMTokenUsage ADD StudentId NVARCHAR(50) NULL;

    IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='LLMTokenUsage' AND COLUMN_NAME='AgentId')
    ALTER TABLE LLMTokenUsage ADD AgentId INT NULL;

    -- Conditional FKs: only add if referenced table exists
    IF OBJECT_ID('StudentConfig', 'U') IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_LLMTokenUsage_Config')
    ALTER TABLE LLMTokenUsage ADD CONSTRAINT FK_LLMTokenUsage_Config
        FOREIGN KEY (StudentConfigId) REFERENCES StudentConfig(Id) ON DELETE CASCADE;

    IF OBJECT_ID('AgentDefinition', 'U') IS NOT NULL
        AND NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = 'FK_LLMTokenUsage_AgentDef')
    ALTER TABLE LLMTokenUsage ADD CONSTRAINT FK_LLMTokenUsage_AgentDef
        FOREIGN KEY (AgentId) REFERENCES AgentDefinition(Id);

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_llm_agent_id' AND object_id = OBJECT_ID('LLMTokenUsage'))
    CREATE INDEX idx_llm_agent_id ON LLMTokenUsage(AgentId);

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_llm_agent_type' AND object_id = OBJECT_ID('LLMTokenUsage'))
    CREATE INDEX idx_llm_agent_type ON LLMTokenUsage(AgentType);

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_llm_created_at' AND object_id = OBJECT_ID('LLMTokenUsage'))
    CREATE INDEX idx_llm_created_at ON LLMTokenUsage(CreatedAt);

    IF NOT EXISTS (SELECT * FROM sys.indexes WHERE name='idx_llm_student_config' AND object_id = OBJECT_ID('LLMTokenUsage'))
    CREATE INDEX idx_llm_student_config ON LLMTokenUsage(StudentConfigId);
    """

    # Student context (nullable — used by NUS repo, optional for template)
    student_config_id: Mapped[int | None] = mapped_column(
        "StudentConfigId",
        Integer,
        nullable=True
    )
    student_id: Mapped[str | None] = mapped_column(
        "StudentId",
        String(50),
        nullable=True
    )

    # Agent context
    agent_id: Mapped[int | None] = mapped_column(
        "AgentId",
        Integer,
        nullable=True
    )
    agent_type: Mapped[str | None] = mapped_column(
        "AgentType",
        String(50),
        nullable=True
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
