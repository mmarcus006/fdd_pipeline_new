"""Database connection utilities for FDD Pipeline."""

from typing import Optional
from supabase import create_client, Client
from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages database connections for the FDD Pipeline."""
    
    def __init__(self):
        self.settings = get_settings()
        self._supabase_client: Optional[Client] = None
        self._sqlalchemy_engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
    
    def get_supabase_client(self) -> Client:
        """Get Supabase client instance."""
        if self._supabase_client is None:
            self._supabase_client = create_client(
                self.settings.supabase_url,
                self.settings.supabase_service_key
            )
            logger.info("Supabase client initialized")
        return self._supabase_client
    
    def get_sqlalchemy_engine(self) -> Engine:
        """Get SQLAlchemy engine for direct SQL operations."""
        if self._sqlalchemy_engine is None:
            # Convert Supabase URL to PostgreSQL connection string
            db_url = self.settings.supabase_url.replace("https://", "postgresql://")
            db_url = f"{db_url}/postgres"
            
            self._sqlalchemy_engine = create_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=self.settings.debug
            )
            logger.info("SQLAlchemy engine initialized")
        return self._sqlalchemy_engine
    
    def get_session_factory(self) -> sessionmaker:
        """Get SQLAlchemy session factory."""
        if self._session_factory is None:
            engine = self.get_sqlalchemy_engine()
            self._session_factory = sessionmaker(bind=engine)
            logger.info("SQLAlchemy session factory initialized")
        return self._session_factory
    
    def get_session(self) -> Session:
        """Get a new SQLAlchemy session."""
        factory = self.get_session_factory()
        return factory()
    
    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            client = self.get_supabase_client()
            # Simple query to test connection
            result = client.table('franchisors').select('id').limit(1).execute()
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error("Database connection test failed", error=str(e))
            return False


# Global database manager instance
db_manager = DatabaseManager()


def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    return db_manager.get_supabase_client()


def get_db_session() -> Session:
    """Get a new database session."""
    return db_manager.get_session()


def test_database_connection() -> bool:
    """Test database connectivity."""
    return db_manager.test_connection()