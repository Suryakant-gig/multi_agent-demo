"""
Database initialization CLI.
Usage:
    python -m app.db.init

Initializes all PostgreSQL tables (or fallback local storage) for InfinityGPT:
- conversations
- messages
- uploaded_files
- datasets
- documents
- document_chunks
- research_sources
- tool_calls
- citations
"""
import sys
from app.utils.logger import logger
from app.utils.config import settings
from app.storage.database import init_db, check_connection, get_engine


def main():
    print("=" * 60)
    print("InfinityGPT Database Initializer")
    print("=" * 60)
    print(f"Target Database URL: {settings.DATABASE_URL or 'sqlite (local default)'}")
    
    health = check_connection()
    print(f"Database Connection Status: {health.get('status')} ({health.get('database')})")

    if health.get("status") != "connected":
        print(f"Warning: Could not connect to primary database: {health.get('error')}")
        print("Falling back to local SQLite database so tables can still be created safely.")

    print("\nCreating tables...")
    try:
        init_db()
        engine = get_engine()
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print("\nSuccessfully initialized database! Created / verified tables:")
        for t in tables:
            print(f"  - {t}")
        print("\nAll database tables ready for production use.")
    except Exception as e:
        print(f"\nError initializing database: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
