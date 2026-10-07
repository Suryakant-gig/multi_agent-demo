import sqlite3
import os
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
from app.utils.config import settings
from app.utils.logger import logger
from app.utils.exceptions import ToolExecutionException


class StorageEngine:
    """
    Manages embedded SQL databases for datasets.
    Solves large file handling by persisting rows into indexed tables,
    enabling paginated retrieval, streaming, and SQL aggregations without high RAM usage.
    """

    def __init__(self, db_dir: Optional[str] = None):
        self.db_dir = db_dir or settings.DB_DIR
        os.makedirs(self.db_dir, exist_ok=True)

    def _get_db_path(self, session_id: str) -> str:
        safe_session_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self.db_dir, f"{safe_session_id}.db")

    def get_connection(self, session_id: str) -> sqlite3.Connection:
        db_path = self._get_db_path(session_id)
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def create_table_from_chunk(self, session_id: str, table_name: str, df_chunk: pd.DataFrame, is_first_chunk: bool = False) -> None:
        db_path = self._get_db_path(session_id)
        with sqlite3.connect(db_path, check_same_thread=False) as conn:
            if_exists = "replace" if is_first_chunk else "append"
            # df_chunk written with index as _row_id
            df_chunk.to_sql(table_name, conn, if_exists=if_exists, index=False)
            
            if is_first_chunk:
                # Add rowid index or create indexes on text and numeric columns
                try:
                    for col in df_chunk.columns[:5]:
                        safe_col = col.replace('"', '""')
                        conn.execute(f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_{safe_col}" ON "{table_name}" ("{safe_col}")')
                except Exception as e:
                    logger.warning(f"Could not create index on {table_name}: {e}")

    def query_paginated(
        self,
        session_id: str,
        table_name: str,
        limit: int = 10,
        offset: int = 0,
        where_clause: Optional[str] = None,
        order_by: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        conn = self.get_connection(session_id)
        try:
            sql = f'SELECT rowid as _row_id, * FROM "{table_name}"'
            if where_clause:
                sql += f" WHERE {where_clause}"
            if order_by:
                sql += f" ORDER BY {order_by}"
            sql += " LIMIT ? OFFSET ?"
            
            cursor = conn.cursor()
            cursor.execute(sql, (limit, offset))
            rows = [dict(row) for row in cursor.fetchall()]
            return rows
        finally:
            conn.close()

    def get_total_count(self, session_id: str, table_name: str, where_clause: Optional[str] = None) -> int:
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
        conn = self.get_connection(session_id)
        valid_funcs = {"SUM", "AVG", "COUNT", "MIN", "MAX"}
        func = agg_func.upper()
        if func not in valid_funcs:
            func = "SUM"

        order_dir = "ASC" if ascending else "DESC"
        try:
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
                LIMIT ?
            '''
            cursor = conn.cursor()
            cursor.execute(sql, (top_k,))
            rows = [dict(row) for row in cursor.fetchall()]
            return rows
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
        """
        conn = self.get_connection(session_id)
        try:
            if not search_terms or not columns:
                return self.query_paginated(session_id, table_name, limit=top_k)

            STOP_WORDS = {"find", "any", "record", "records", "about", "the", "a", "an", "in", "of", "for", "show", "me", "what", "which", "where", "is", "are", "get", "all", "please", "item", "items", "data"}
            filtered_terms = [t for t in search_terms if t.lower() not in STOP_WORDS]
            terms_to_use = filtered_terms if filtered_terms else search_terms

            conditions = []
            params = []
            for term in terms_to_use:
                term_clause = []
                for col in columns:
                    safe_col = col.replace('"', '""')
                    term_clause.append(f'CAST("{safe_col}" AS TEXT) LIKE ?')
                    params.append(f"%{term}%")
                if term_clause:
                    conditions.append(f"({' OR '.join(term_clause)})")

            where_str = " OR ".join(conditions) if conditions else "1=1"
            sql = f'SELECT rowid as _row_id, * FROM "{table_name}" WHERE {where_str} LIMIT ?'
            params.append(top_k)

            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def execute_read_query(self, session_id: str, sql: str, params: Optional[Tuple] = None) -> List[Dict[str, Any]]:
        # Enforce read-only restriction for safety
        cleaned_sql = sql.strip().upper()
        if not cleaned_sql.startswith("SELECT") and not cleaned_sql.startswith("WITH"):
            raise ToolExecutionException("sql_tool", "Only SELECT/WITH read queries are allowed for security.")

        conn = self.get_connection(session_id)
        try:
            cursor = conn.cursor()
            cursor.execute(sql, params or ())
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            raise ToolExecutionException("sql_tool", f"SQL execution error: {str(e)}")
        finally:
            conn.close()


storage_engine = StorageEngine()
