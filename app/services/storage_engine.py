import os
import sqlite3
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from sqlalchemy import text
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import ToolExecutionException
from app.storage.database import get_engine, check_connection


def _clean_row(row_dict: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = {}
    for k, v in row_dict.items():
        if isinstance(v, Decimal):
            cleaned[k] = int(v) if v % 1 == 0 else float(v)
        else:
            cleaned[k] = v
    return cleaned


class StorageEngine:
    """
    Manages persistent tabular data tables and query execution.
    Supports both central PostgreSQL storage and local SQLite fallback.
    Maintains chunked/streamed insertion to handle large CSV/Excel files with low RAM usage.
    """

    def __init__(self, db_dir: Optional[str] = None):
        self.db_dir = db_dir or settings.DB_DIR
        os.makedirs(self.db_dir, exist_ok=True)
        self._row_offsets: Dict[str, int] = {}

    def _get_sqlite_path(self, session_id: str) -> str:
        safe_session_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self.db_dir, f"{safe_session_id}.db")

    def get_connection(self, session_id: str) -> sqlite3.Connection:
        db_path = self._get_sqlite_path(session_id)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_table_from_chunk(
        self,
        session_id: str,
        table_name: str,
        df_chunk: pd.DataFrame,
        is_first_chunk: bool = False
    ) -> None:
        """
        Streams and bulk-inserts DataFrame chunks into persistent tables.
        Injects a persistent `_row_id` column to guarantee uniform pagination and citations across engines.
        """
        if is_first_chunk:
            self._row_offsets[table_name] = 0

        current_offset = self._row_offsets.get(table_name, 0)
        chunk_to_write = df_chunk.copy()
        
        # Ensure _row_id is explicitly stored
        if "_row_id" not in chunk_to_write.columns:
            chunk_to_write.insert(0, "_row_id", range(current_offset + 1, current_offset + 1 + len(chunk_to_write)))
        self._row_offsets[table_name] = current_offset + len(chunk_to_write)

        if_exists = "replace" if is_first_chunk else "append"

        # 1. Primary write to SQLAlchemy engine (PostgreSQL or SQLite)
        try:
            engine = get_engine()
            chunk_to_write.to_sql(table_name, con=engine, if_exists=if_exists, index=False)
            if is_first_chunk:
                with engine.connect() as conn:
                    for col in chunk_to_write.columns[:5]:
                        if col == "_row_id":
                            continue
                        safe_col = col.replace('"', '""')
                        idx_name = f"idx_{table_name[:20]}_{safe_col[:20]}".replace(" ", "_")
                        try:
                            conn.execute(text(f'CREATE INDEX IF NOT EXISTS "{idx_name}" ON "{table_name}" ("{safe_col}")'))
                            conn.commit()
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"Could not write tabular chunk to SQLAlchemy engine: {e}")

        # 2. Local session SQLite backup for instant isolated queries
        db_path = self._get_sqlite_path(session_id)
        with sqlite3.connect(db_path, check_same_thread=False) as conn:
            chunk_to_write.to_sql(table_name, conn, if_exists=if_exists, index=False)
            if is_first_chunk:
                try:
                    for col in chunk_to_write.columns[:5]:
                        safe_col = col.replace('"', '""')
                        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_{safe_col}" ON "{table_name}" ("{safe_col}")')
                except Exception as e:
                    logger.warning(f"Could not create SQLite index on {table_name}: {e}")

    def query_paginated(
        self,
        session_id: str,
        table_name: str,
        limit: int = 10,
        offset: int = 0,
        where_clause: Optional[str] = None,
        order_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        # Query central engine first if available
        try:
            engine = get_engine()
            sql = f'SELECT * FROM "{table_name}"'
            if where_clause:
                sql += f" WHERE {where_clause}"
            if order_by:
                sql += f" ORDER BY {order_by}"
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                return [_clean_row(dict(row._mapping)) for row in result]
        except Exception as e:
            logger.debug(f"Querying SQLite fallback for {table_name}: {e}")

        # Fallback to local session SQLite
        conn = self.get_connection(session_id)
        try:
            sql = f'SELECT _row_id, * FROM "{table_name}"' if "_row_id" in [c[1] for c in conn.execute(f'PRAGMA table_info("{table_name}")').fetchall()] else f'SELECT rowid as _row_id, * FROM "{table_name}"'
            if where_clause:
                sql += f" WHERE {where_clause}"
            if order_by:
                sql += f" ORDER BY {order_by}"
            sql += " LIMIT ? OFFSET ?"
            cursor = conn.cursor()
            cursor.execute(sql, (limit, offset))
            return [_clean_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_total_count(self, session_id: str, table_name: str, where_clause: Optional[str] = None) -> int:
        try:
            engine = get_engine()
            sql = f'SELECT COUNT(*) as cnt FROM "{table_name}"'
            if where_clause:
                sql += f" WHERE {where_clause}"
            with engine.connect() as conn:
                row = conn.execute(text(sql)).fetchone()
                return int(row[0]) if row else 0
        except Exception:
            pass

        conn = self.get_connection(session_id)
        try:
            sql = f'SELECT COUNT(*) as cnt FROM "{table_name}"'
            if where_clause:
                sql += f" WHERE {where_clause}"
            cursor = conn.cursor()
            cursor.execute(sql)
            row = cursor.fetchone()
            return int(row["cnt"]) if row else 0
        finally:
            conn.close()

    def execute_aggregation(
        self,
        session_id: str,
        table_name: str,
        group_by_col: str,
        agg_col: str,
        agg_func: str = "SUM",
        top_k: int = 5,
        ascending: bool = False
    ) -> List[Dict[str, Any]]:
        valid_funcs = {"SUM", "AVG", "COUNT", "MIN", "MAX"}
        func = agg_func.upper() if agg_func.upper() in valid_funcs else "SUM"
        order_dir = "ASC" if ascending else "DESC"
        safe_group = group_by_col.replace('"', '""')
        safe_agg = agg_col.replace('"', '""')

        sql = f'''
            SELECT 
                "{safe_group}" as category,
                {func}("{safe_agg}") as metric,
                COUNT(*) as row_count
            FROM "{table_name}"
            WHERE "{safe_group}" IS NOT NULL AND "{safe_agg}" IS NOT NULL
            GROUP BY "{safe_group}"
            ORDER BY metric {order_dir}
            LIMIT {int(top_k)}
        '''

        try:
            engine = get_engine()
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                return [_clean_row(dict(row._mapping)) for row in result]
        except Exception as e:
            logger.debug(f"Aggregation using SQLite fallback: {e}")

        conn = self.get_connection(session_id)
        try:
            cursor = conn.cursor()
            cursor.execute(sql.replace(f"LIMIT {int(top_k)}", "LIMIT ?"), (top_k,))
            return [_clean_row(dict(row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_records(
        self,
        session_id: str,
        table_name: str,
        search_terms: List[str],
        columns: List[str],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Retrieves matching rows via column pattern matching and text queries.
        Uses LOWER(CAST(... AS TEXT)) to ensure case-insensitive matching across both PostgreSQL and SQLite.
        """
        if not search_terms or not columns:
            return self.query_paginated(session_id, table_name, limit=top_k)

        STOP_WORDS = {"find", "any", "record", "records", "about", "the", "a", "an", "in", "of", "for", "show", "me", "what", "which", "where", "is", "are", "get", "all", "please", "item", "items", "data"}
        filtered_terms = [t for t in search_terms if t.lower() not in STOP_WORDS]
        terms_to_use = filtered_terms if filtered_terms else search_terms

        conditions = []
        for term in terms_to_use:
            term_clause = []
            safe_term = term.replace("'", "''").lower()
            for col in columns:
                safe_col = col.replace('"', '""')
                term_clause.append(f'LOWER(CAST("{safe_col}" AS TEXT)) LIKE \'%{safe_term}%\'')
            if term_clause:
                conditions.append(f"({' OR '.join(term_clause)})")

        where_str = " OR ".join(conditions) if conditions else "1=1"
        return self.query_paginated(session_id, table_name, limit=top_k, where_clause=where_str)

    def execute_read_query(self, session_id: str, sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        cleaned_sql = sql.strip().upper()
        if not cleaned_sql.startswith("SELECT") and not cleaned_sql.startswith("WITH"):
            raise ToolExecutionException("sql_tool", "Only SELECT/WITH read queries are allowed for security.")

        try:
            engine = get_engine()
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                return [_clean_row(dict(row._mapping)) for row in result]
        except Exception:
            pass

        conn = self.get_connection(session_id)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params or ())
            return [_clean_row(dict(row)) for row in cursor.fetchall()]
        except Exception as e:
            raise ToolExecutionException("sql_tool", f"SQL execution error: {str(e)}")
        finally:
            conn.close()


storage_engine = StorageEngine()
