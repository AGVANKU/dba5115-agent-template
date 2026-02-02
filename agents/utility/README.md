# Utility

Database access, ORM models, and notification routing.

## Files

| File | Purpose |
|------|---------|
| `util_database.py` | SQLAlchemy engine, session management, generic CRUD |
| `util_datamodel.py` | ORM models: AgentDefinition, AgentPromptRegistry, AgentToolMapping, LLMTokenUsage |
| `util_notifications.py` | Notification recipient routing |

## Database

Uses SQL Server via SQLAlchemy + pyodbc. The database connection is configured via environment variables:
- `DB_SERVER`, `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`

### Generic Operations

```python
from agents.utility.util_database import ensure_table, upsert, get_by_id, delete_by_id

# Ensure table exists (idempotent)
ensure_table(LLMTokenUsage)

# Upsert a record (uses model's __upsert_keys__)
upsert(MyModel, {"field1": "value1", "field2": "value2"})

# Get by ID
get_by_id(MyModel, 42)

# Delete by ID
delete_by_id(MyModel, 42)
```

## ORM Models

### Adding a New Model

1. Inherit from `BaseModel` (provides Id, CreatedAt, UpdatedAt)
2. Define `__tablename__`, `__create_sql__`, and optionally `__upsert_keys__`
3. Call `ensure_table(MyModel)` on startup

```python
class MyModel(BaseModel):
    __tablename__ = "MyTable"
    __upsert_keys__ = ["unique_field"]
    __create_sql__ = """
    IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='MyTable' AND xtype='U')
    CREATE TABLE MyTable (
        Id INT IDENTITY(1,1) PRIMARY KEY,
        UniqueField NVARCHAR(100) NOT NULL,
        CreatedAt DATETIME NOT NULL DEFAULT GETDATE(),
        UpdatedAt DATETIME
    )
    """
    unique_field: Mapped[str] = mapped_column("UniqueField", String(100), nullable=False)
```

## Token Tracking

The `LLMTokenUsage` model records every agent invocation with:
- Agent type and operation
- Model name, input/output token counts
- Start/completion timestamps
- Number of inference rounds
