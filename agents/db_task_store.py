"""
Provides a configured instance of the ADK's SqliteSessionService.

Updated to use SqliteSessionService (async aiosqlite) instead of DatabaseSessionService.
This is the recommended approach for SQLite as per ADK latest updates.
"""
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from utils.config import get_settings


def get_db_session_service() -> SqliteSessionService:
    """
    Returns a configured instance of the ADK's SqliteSessionService.
    
    This service is required by ADK v1.19.0 and later. It uses aiosqlite
    for asynchronous access to a SQLite database for persistent task storage.

    SqliteSessionService:
    - Uses aiosqlite (async SQLite driver)
    - Stores event data as JSON in a single column
    - Fixed schema that avoids DB migrations for future Event object changes
    - Recommended for SQLite-based ADK applications
    """
    # The database URL for sqlite from Pydantic settings is "sqlite:///./data/asx_scraper.db"
    # The aiosqlite library expects just the file path for a local database.
    db_url = get_settings().database_url
    
    if db_url.startswith("sqlite:///"):
        db_path = db_url[len("sqlite:///"):]
    else:
        db_path = db_url # Assume it's already a path

    return SqliteSessionService(db_path=db_path)
