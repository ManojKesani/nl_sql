from pydantic import BaseModel, Field


class SQLResponse(BaseModel):
    thought_process: str = Field(description="Brief reasoning: tables, joins, filters, assumptions.")
    sql: str = Field(description="The final SQLite query exactly as run with query_database. Empty only if unanswerable.")
    answer: str = Field(description="Plain-English answer based ONLY on returned rows.")