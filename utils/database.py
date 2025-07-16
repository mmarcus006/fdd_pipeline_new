"""Database connection utilities and operations for FDD Pipeline."""

import time
from contextlib import contextmanager
from typing import Optional, Dict, List, Any, Union, Type, TypeVar, Generic, Callable
from uuid import UUID
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor

from supabase import create_client, Client
from sqlalchemy import create_engine, Engine, text, inspect, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from sqlalchemy.pool import QueuePool
from pydantic import BaseModel

from config import get_settings
from utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)


class DatabaseHealthCheck:
    """Database health monitoring utilities."""

    def __init__(self, db_manager: "DatabaseManager"):
        self.db_manager = db_manager

    def check_connection(self) -> Dict[str, Any]:
        """Comprehensive connection health check."""
        start_time = time.time()
        result = {
            "healthy": False,
            "response_time_ms": 0,
            "supabase_connection": False,
            "sqlalchemy_connection": False,
            "pool_status": {},
            "error": None,
        }

        try:
            # Test Supabase connection
            client = self.db_manager.get_supabase_client()
            client.table("franchisors").select("id").limit(1).execute()
            result["supabase_connection"] = True

            # Test SQLAlchemy connection
            with self.db_manager.get_session() as session:
                session.execute(text("SELECT 1"))
                result["sqlalchemy_connection"] = True

            # Get pool status
            engine = self.db_manager.get_sqlalchemy_engine()
            if hasattr(engine.pool, "status"):
                pool = engine.pool
                result["pool_status"] = {
                    "size": pool.size(),
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                    "invalid": pool.invalid(),
                }

            result["healthy"] = True

        except Exception as e:
            result["error"] = str(e)
            logger.error("Database health check failed", error=str(e))

        result["response_time_ms"] = int((time.time() - start_time) * 1000)
        return result

    def check_table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        try:
            engine = self.db_manager.get_sqlalchemy_engine()
            inspector = inspect(engine)
            return table_name in inspector.get_table_names()
        except Exception as e:
            logger.error(
                "Failed to check table existence", table=table_name, error=str(e)
            )
            return False


class QueryBuilder:
    """Advanced query builder for common data access patterns."""

    def __init__(self, db_manager: "DatabaseManager"):
        self.db = db_manager
        self._table_name: Optional[str] = None
        self._select_fields: List[str] = ["*"]
        self._filters: List[Dict[str, Any]] = []
        self._joins: List[Dict[str, Any]] = []
        self._order_by: List[str] = []
        self._limit_value: Optional[int] = None
        self._offset_value: Optional[int] = None

    def table(self, table_name: str) -> "QueryBuilder":
        """Set the table name."""
        self._table_name = table_name
        return self

    def select(self, *fields: str) -> "QueryBuilder":
        """Set fields to select."""
        self._select_fields = list(fields) if fields else ["*"]
        return self

    def where(
        self, column: str, operator: str = "=", value: Any = None
    ) -> "QueryBuilder":
        """Add WHERE condition."""
        self._filters.append({"column": column, "operator": operator, "value": value})
        return self

    def where_in(self, column: str, values: List[Any]) -> "QueryBuilder":
        """Add WHERE IN condition."""
        self._filters.append({"column": column, "operator": "in", "value": values})
        return self

    def where_between(self, column: str, start: Any, end: Any) -> "QueryBuilder":
        """Add WHERE BETWEEN condition."""
        self._filters.append(
            {"column": column, "operator": "between", "value": [start, end]}
        )
        return self

    def where_null(self, column: str, is_null: bool = True) -> "QueryBuilder":
        """Add WHERE NULL/NOT NULL condition."""
        self._filters.append(
            {
                "column": column,
                "operator": "is_null" if is_null else "is_not_null",
                "value": None,
            }
        )
        return self

    def join(
        self, table: str, on_condition: str, join_type: str = "inner"
    ) -> "QueryBuilder":
        """Add JOIN clause."""
        self._joins.append(
            {"table": table, "condition": on_condition, "type": join_type}
        )
        return self

    def order_by(self, column: str, direction: str = "asc") -> "QueryBuilder":
        """Add ORDER BY clause."""
        self._order_by.append(f"{column} {direction.upper()}")
        return self

    def limit(self, count: int) -> "QueryBuilder":
        """Set LIMIT."""
        self._limit_value = count
        return self

    def offset(self, count: int) -> "QueryBuilder":
        """Set OFFSET."""
        self._offset_value = count
        return self

    def build_sql(self) -> tuple[str, Dict[str, Any]]:
        """Build SQL query and parameters."""
        if not self._table_name:
            raise ValueError("Table name is required")

        # Build SELECT clause
        fields = ", ".join(self._select_fields)
        sql_parts = [f"SELECT {fields}"]

        # Build FROM clause
        sql_parts.append(f"FROM {self._table_name}")

        # Build JOIN clauses
        for join in self._joins:
            join_type = join["type"].upper()
            sql_parts.append(f"{join_type} JOIN {join['table']} ON {join['condition']}")

        # Build WHERE clause
        params = {}
        if self._filters:
            where_conditions = []
            for i, filter_item in enumerate(self._filters):
                param_key = f"param_{i}"
                column = filter_item["column"]
                operator = filter_item["operator"]
                value = filter_item["value"]

                if operator == "=":
                    where_conditions.append(f"{column} = :{param_key}")
                    params[param_key] = value
                elif operator == "in":
                    placeholders = ", ".join(
                        [f":{param_key}_{j}" for j in range(len(value))]
                    )
                    where_conditions.append(f"{column} IN ({placeholders})")
                    for j, v in enumerate(value):
                        params[f"{param_key}_{j}"] = v
                elif operator == "between":
                    where_conditions.append(
                        f"{column} BETWEEN :{param_key}_start AND :{param_key}_end"
                    )
                    params[f"{param_key}_start"] = value[0]
                    params[f"{param_key}_end"] = value[1]
                elif operator == "is_null":
                    where_conditions.append(f"{column} IS NULL")
                elif operator == "is_not_null":
                    where_conditions.append(f"{column} IS NOT NULL")
                elif operator in [">", "<", ">=", "<=", "!=", "LIKE", "ILIKE"]:
                    where_conditions.append(f"{column} {operator} :{param_key}")
                    params[param_key] = value

            if where_conditions:
                sql_parts.append(f"WHERE {' AND '.join(where_conditions)}")

        # Build ORDER BY clause
        if self._order_by:
            sql_parts.append(f"ORDER BY {', '.join(self._order_by)}")

        # Build LIMIT clause
        if self._limit_value:
            sql_parts.append(f"LIMIT {self._limit_value}")

        # Build OFFSET clause
        if self._offset_value:
            sql_parts.append(f"OFFSET {self._offset_value}")

        return " ".join(sql_parts), params

    def execute(self) -> List[Dict[str, Any]]:
        """Execute the built query."""
        sql, params = self.build_sql()
        return self.db.execute_query(sql, params)

    def first(self) -> Optional[Dict[str, Any]]:
        """Execute query and return first result."""
        results = self.limit(1).execute()
        return results[0] if results else None

    def count(self) -> int:
        """Execute count query."""
        original_fields = self._select_fields
        self._select_fields = ["COUNT(*) as count"]

        try:
            result = self.first()
            return result["count"] if result else 0
        finally:
            self._select_fields = original_fields


class BatchOperations:
    """Optimized batch operations for high-performance data processing."""

    def __init__(self, db_manager: "DatabaseManager"):
        self.db = db_manager
        self.batch_size = 1000
        self.thread_pool = ThreadPoolExecutor(max_workers=4)

    def batch_insert_chunked(
        self, table_name: str, records: List[Dict], chunk_size: Optional[int] = None
    ) -> int:
        """Insert records in optimized chunks."""
        if not records:
            return 0

        chunk_size = chunk_size or self.batch_size
        total_inserted = 0

        try:
            # Process in chunks
            for i in range(0, len(records), chunk_size):
                chunk = records[i : i + chunk_size]
                inserted = self.db.execute_batch_insert(table_name, chunk)
                total_inserted += inserted

                logger.debug(
                    "Batch chunk processed",
                    table=table_name,
                    chunk_size=len(chunk),
                    total_processed=i + len(chunk),
                )

            logger.info(
                "Batch insert completed",
                table=table_name,
                total_records=len(records),
                total_inserted=total_inserted,
            )

            return total_inserted

        except Exception as e:
            logger.error(
                "Batch insert failed",
                table=table_name,
                total_records=len(records),
                error=str(e),
            )
            raise

    def batch_upsert(
        self,
        table_name: str,
        records: List[Dict],
        conflict_columns: List[str],
        chunk_size: Optional[int] = None,
    ) -> int:
        """Upsert records in batches."""
        if not records:
            return 0

        chunk_size = chunk_size or self.batch_size
        total_processed = 0

        try:
            client = self.db.get_supabase_client()

            # Process in chunks
            for i in range(0, len(records), chunk_size):
                chunk = records[i : i + chunk_size]

                response = (
                    client.table(table_name)
                    .upsert(chunk, on_conflict=",".join(conflict_columns))
                    .execute()
                )

                processed = len(response.data) if response.data else 0
                total_processed += processed

                logger.debug(
                    "Batch upsert chunk processed",
                    table=table_name,
                    chunk_size=len(chunk),
                    total_processed=i + len(chunk),
                )

            logger.info(
                "Batch upsert completed",
                table=table_name,
                total_records=len(records),
                total_processed=total_processed,
            )

            return total_processed

        except Exception as e:
            logger.error(
                "Batch upsert failed",
                table=table_name,
                total_records=len(records),
                error=str(e),
            )
            raise

    def batch_update_by_ids(
        self, table_name: str, updates: List[Dict[str, Any]]
    ) -> int:
        """Update multiple records by ID."""
        if not updates:
            return 0

        total_updated = 0

        try:
            with self.db.transaction() as session:
                for update_data in updates:
                    record_id = update_data.pop("id")

                    # Build update query
                    set_clauses = []
                    params = {"record_id": record_id}

                    for i, (column, value) in enumerate(update_data.items()):
                        param_key = f"value_{i}"
                        set_clauses.append(f"{column} = :{param_key}")
                        params[param_key] = value

                    if set_clauses:
                        sql = f"""
                        UPDATE {table_name} 
                        SET {', '.join(set_clauses)}
                        WHERE id = :record_id
                        """

                        result = session.execute(text(sql), params)
                        total_updated += result.rowcount

                logger.info(
                    "Batch update completed",
                    table=table_name,
                    total_updated=total_updated,
                )

                return total_updated

        except Exception as e:
            logger.error("Batch update failed", table=table_name, error=str(e))
            raise

    def batch_delete_by_ids(
        self, table_name: str, record_ids: List[Union[str, UUID]]
    ) -> int:
        """Delete multiple records by ID."""
        if not record_ids:
            return 0

        try:
            client = self.db.get_supabase_client()
            str_ids = [str(rid) for rid in record_ids]

            response = client.table(table_name).delete().in_("id", str_ids).execute()

            deleted_count = len(response.data) if response.data else 0

            logger.info(
                "Batch delete completed",
                table=table_name,
                requested_deletes=len(record_ids),
                actual_deletes=deleted_count,
            )

            return deleted_count

        except Exception as e:
            logger.error(
                "Batch delete failed",
                table=table_name,
                record_count=len(record_ids),
                error=str(e),
            )
            raise


class DatabaseManager:
    """Enhanced database manager with CRUD operations and connection pooling."""

    def __init__(self):
        self.settings = get_settings()
        self._supabase_client: Optional[Client] = None
        self._sqlalchemy_engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._health_check = DatabaseHealthCheck(self)
        self._query_builder = QueryBuilder(self)
        self._batch_ops = BatchOperations(self)

    @property
    def health_check(self) -> DatabaseHealthCheck:
        """Get health check utilities."""
        return self._health_check

    def get_supabase_client(self) -> Client:
        """Get Supabase client instance with lazy initialization."""
        if self._supabase_client is None:
            try:
                self._supabase_client = create_client(
                    self.settings.supabase_url, self.settings.supabase_service_key
                )
                logger.info("Supabase client initialized successfully")
            except Exception as e:
                logger.error("Failed to initialize Supabase client", error=str(e))
                raise
        return self._supabase_client

    def get_sqlalchemy_engine(self) -> Engine:
        """Get SQLAlchemy engine with connection pooling."""
        if self._sqlalchemy_engine is None:
            try:
                # Build PostgreSQL connection string from Supabase URL
                base_url = self.settings.supabase_url.replace("https://", "")
                db_url = f"postgresql://postgres:{self.settings.supabase_service_key}@{base_url}/postgres"

                self._sqlalchemy_engine = create_engine(
                    db_url,
                    poolclass=QueuePool,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=3600,  # Recycle connections after 1 hour
                    echo=self.settings.debug,
                    connect_args={
                        "connect_timeout": 10,
                        "application_name": "fdd-pipeline",
                    },
                )
                logger.info("SQLAlchemy engine initialized with connection pooling")
            except Exception as e:
                logger.error("Failed to initialize SQLAlchemy engine", error=str(e))
                raise
        return self._sqlalchemy_engine

    def get_session_factory(self) -> sessionmaker:
        """Get SQLAlchemy session factory."""
        if self._session_factory is None:
            engine = self.get_sqlalchemy_engine()
            self._session_factory = sessionmaker(
                bind=engine, expire_on_commit=False, autoflush=True, autocommit=False
            )
            logger.debug("SQLAlchemy session factory initialized")
        return self._session_factory

    @contextmanager
    def get_session(self):
        """Get a database session with automatic cleanup."""
        session = None
        try:
            factory = self.get_session_factory()
            session = factory()
            yield session
            session.commit()
        except Exception as e:
            if session:
                session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            if session:
                session.close()

    def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute a raw SQL query and return results."""
        try:
            with self.get_session() as session:
                result = session.execute(text(query), params or {})
                if result.returns_rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in result.fetchall()]
                return []
        except Exception as e:
            logger.error("Query execution failed", query=query, error=str(e))
            raise

    def execute_batch_insert(self, table_name: str, records: List[Dict]) -> int:
        """Execute batch insert with optimized performance."""
        if not records:
            return 0

        try:
            client = self.get_supabase_client()
            response = client.table(table_name).insert(records).execute()

            inserted_count = len(response.data) if response.data else 0
            logger.info(
                "Batch insert completed",
                table=table_name,
                records_inserted=inserted_count,
            )
            return inserted_count

        except Exception as e:
            logger.error(
                "Batch insert failed",
                table=table_name,
                record_count=len(records),
                error=str(e),
            )
            raise

    def upsert_record(
        self, table_name: str, record: Dict, conflict_columns: List[str]
    ) -> Dict:
        """Upsert a single record with conflict resolution."""
        try:
            client = self.get_supabase_client()
            response = (
                client.table(table_name)
                .upsert(record, on_conflict=",".join(conflict_columns))
                .execute()
            )

            if response.data:
                logger.debug(
                    "Record upserted successfully",
                    table=table_name,
                    record_id=record.get("id"),
                )
                return response.data[0]
            else:
                raise ValueError("Upsert returned no data")

        except Exception as e:
            logger.error(
                "Upsert failed",
                table=table_name,
                conflict_columns=conflict_columns,
                error=str(e),
            )
            raise

    def get_record_by_id(
        self, table_name: str, record_id: Union[str, UUID]
    ) -> Optional[Dict]:
        """Get a single record by ID."""
        try:
            client = self.get_supabase_client()
            response = (
                client.table(table_name).select("*").eq("id", str(record_id)).execute()
            )

            if response.data:
                return response.data[0]
            return None

        except Exception as e:
            logger.error(
                "Failed to get record by ID",
                table=table_name,
                record_id=str(record_id),
                error=str(e),
            )
            raise

    def get_records_by_filter(
        self,
        table_name: str,
        filters: Dict,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[Dict]:
        """Get records with filtering and ordering."""
        try:
            client = self.get_supabase_client()
            query = client.table(table_name).select("*")

            # Apply filters
            for column, value in filters.items():
                if isinstance(value, list):
                    query = query.in_(column, value)
                else:
                    query = query.eq(column, value)

            # Apply ordering
            if order_by:
                query = query.order(order_by)

            # Apply limit
            if limit:
                query = query.limit(limit)

            response = query.execute()
            return response.data or []

        except Exception as e:
            logger.error(
                "Failed to get records by filter",
                table=table_name,
                filters=filters,
                error=str(e),
            )
            raise

    def update_record(
        self, table_name: str, record_id: Union[str, UUID], updates: Dict
    ) -> Optional[Dict]:
        """Update a single record by ID."""
        try:
            client = self.get_supabase_client()
            response = (
                client.table(table_name)
                .update(updates)
                .eq("id", str(record_id))
                .execute()
            )

            if response.data:
                logger.debug(
                    "Record updated successfully",
                    table=table_name,
                    record_id=str(record_id),
                )
                return response.data[0]
            return None

        except Exception as e:
            logger.error(
                "Failed to update record",
                table=table_name,
                record_id=str(record_id),
                error=str(e),
            )
            raise

    def delete_record(self, table_name: str, record_id: Union[str, UUID]) -> bool:
        """Delete a single record by ID."""
        try:
            client = self.get_supabase_client()
            response = (
                client.table(table_name).delete().eq("id", str(record_id)).execute()
            )

            success = response.data is not None
            if success:
                logger.info(
                    "Record deleted successfully",
                    table=table_name,
                    record_id=str(record_id),
                )
            return success

        except Exception as e:
            logger.error(
                "Failed to delete record",
                table=table_name,
                record_id=str(record_id),
                error=str(e),
            )
            raise

    def count_records(self, table_name: str, filters: Optional[Dict] = None) -> int:
        """Count records with optional filtering."""
        try:
            client = self.get_supabase_client()
            query = client.table(table_name).select("*", count="exact")

            if filters:
                for column, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(column, value)
                    else:
                        query = query.eq(column, value)

            response = query.execute()
            return response.count or 0

        except Exception as e:
            logger.error(
                "Failed to count records",
                table=table_name,
                filters=filters,
                error=str(e),
            )
            raise

    @contextmanager
    def transaction(self):
        """Database transaction context manager."""
        with self.get_session() as session:
            try:
                yield session
                session.commit()
                logger.debug("Transaction committed successfully")
            except Exception as e:
                session.rollback()
                logger.error("Transaction rolled back", error=str(e))
                raise

    def test_connection(self) -> bool:
        """Test database connectivity."""
        try:
            health = self.health_check.check_connection()
            return health["healthy"]
        except Exception as e:
            logger.error("Connection test failed", error=str(e))
            return False

    # Enhanced query builder access
    def query(self) -> QueryBuilder:
        """Get a new query builder instance."""
        return QueryBuilder(self)

    # Enhanced batch operations access
    @property
    def batch(self) -> BatchOperations:
        """Get batch operations utilities."""
        return self._batch_ops

    # Connection monitoring methods
    def get_connection_pool_status(self) -> Dict[str, Any]:
        """Get detailed connection pool status."""
        try:
            engine = self.get_sqlalchemy_engine()
            pool = engine.pool

            return {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid(),
                "total_connections": pool.size() + pool.overflow(),
                "available_connections": pool.checkedin(),
                "active_connections": pool.checkedout(),
            }
        except Exception as e:
            logger.error("Failed to get pool status", error=str(e))
            return {}

    def reset_connection_pool(self) -> bool:
        """Reset the connection pool (useful for connection issues)."""
        try:
            if self._sqlalchemy_engine:
                self._sqlalchemy_engine.dispose()
                self._sqlalchemy_engine = None
                self._session_factory = None
                logger.info("Connection pool reset successfully")
                return True
        except Exception as e:
            logger.error("Failed to reset connection pool", error=str(e))
        return False

    # Advanced query methods
    def execute_query_with_retry(
        self, query: str, params: Optional[Dict] = None, max_retries: int = 3
    ) -> List[Dict]:
        """Execute query with automatic retry on connection failures."""
        last_exception = None

        for attempt in range(max_retries):
            try:
                return self.execute_query(query, params)
            except (OperationalError, IntegrityError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt  # Exponential backoff
                    logger.warning(
                        f"Query failed, retrying in {wait_time}s",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    time.sleep(wait_time)

                    # Reset connection pool on connection errors
                    if "connection" in str(e).lower():
                        self.reset_connection_pool()
                else:
                    logger.error(
                        "Query failed after all retries",
                        query=query,
                        attempts=max_retries,
                        error=str(e),
                    )

        raise last_exception

    def execute_transaction_with_retry(
        self, operations: Callable[[Session], Any], max_retries: int = 3
    ) -> Any:
        """Execute transaction with automatic retry."""
        last_exception = None

        for attempt in range(max_retries):
            try:
                with self.transaction() as session:
                    return operations(session)
            except (OperationalError, IntegrityError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2**attempt
                    logger.warning(
                        f"Transaction failed, retrying in {wait_time}s",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    time.sleep(wait_time)

                    if "connection" in str(e).lower():
                        self.reset_connection_pool()
                else:
                    logger.error(
                        "Transaction failed after all retries",
                        attempts=max_retries,
                        error=str(e),
                    )

        raise last_exception

    # Advanced query patterns for common use cases
    def get_records_paginated(
        self,
        table_name: str,
        page: int = 1,
        page_size: int = 50,
        filters: Optional[Dict] = None,
        order_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get paginated records with metadata."""
        try:
            offset = (page - 1) * page_size

            # Get total count
            total_count = self.count_records(table_name, filters)

            # Get records for current page
            client = self.get_supabase_client()
            query = client.table(table_name).select("*")

            # Apply filters
            if filters:
                for column, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(column, value)
                    else:
                        query = query.eq(column, value)

            # Apply ordering
            if order_by:
                query = query.order(order_by)

            # Apply pagination
            query = query.range(offset, offset + page_size - 1)

            response = query.execute()
            records = response.data or []

            # Calculate pagination metadata
            total_pages = (total_count + page_size - 1) // page_size
            has_next = page < total_pages
            has_prev = page > 1

            return {
                "records": records,
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": total_count,
                    "total_pages": total_pages,
                    "has_next": has_next,
                    "has_prev": has_prev,
                },
            }

        except Exception as e:
            logger.error(
                "Failed to get paginated records",
                table=table_name,
                page=page,
                error=str(e),
            )
            raise

    def bulk_update_by_condition(
        self, table_name: str, updates: Dict[str, Any], condition: Dict[str, Any]
    ) -> int:
        """Update multiple records matching a condition."""
        try:
            with self.get_session() as session:
                # Build update query
                set_clauses = []
                params = {}

                # Add update values
                for i, (column, value) in enumerate(updates.items()):
                    param_key = f"update_value_{i}"
                    set_clauses.append(f"{column} = :{param_key}")
                    params[param_key] = value

                # Add condition values
                where_clauses = []
                for i, (column, value) in enumerate(condition.items()):
                    param_key = f"condition_value_{i}"
                    where_clauses.append(f"{column} = :{param_key}")
                    params[param_key] = value

                sql = f"""
                UPDATE {table_name} 
                SET {', '.join(set_clauses)}
                WHERE {' AND '.join(where_clauses)}
                """

                result = session.execute(text(sql), params)
                updated_count = result.rowcount

                logger.info(
                    "Bulk update completed",
                    table=table_name,
                    updated_count=updated_count,
                    condition=condition,
                )

                return updated_count

        except Exception as e:
            logger.error(
                "Bulk update failed",
                table=table_name,
                condition=condition,
                error=str(e),
            )
            raise

    def execute_stored_procedure(
        self, procedure_name: str, params: Optional[Dict] = None
    ) -> List[Dict]:
        """Execute a stored procedure."""
        try:
            with self.get_session() as session:
                # Build procedure call
                if params:
                    param_placeholders = ", ".join([f":{key}" for key in params.keys()])
                    sql = f"SELECT * FROM {procedure_name}({param_placeholders})"
                else:
                    sql = f"SELECT * FROM {procedure_name}()"

                result = session.execute(text(sql), params or {})

                if result.returns_rows:
                    columns = result.keys()
                    return [dict(zip(columns, row)) for row in result.fetchall()]
                return []

        except Exception as e:
            logger.error(
                "Stored procedure execution failed",
                procedure=procedure_name,
                error=str(e),
            )
            raise

    def get_table_statistics(self, table_name: str) -> Dict[str, Any]:
        """Get comprehensive table statistics."""
        try:
            with self.get_session() as session:
                # Get basic table info
                table_info_sql = f"""
                SELECT 
                    schemaname,
                    tablename,
                    tableowner,
                    hasindexes,
                    hasrules,
                    hastriggers
                FROM pg_tables 
                WHERE tablename = :table_name
                """

                table_info = session.execute(
                    text(table_info_sql), {"table_name": table_name}
                ).fetchone()

                if not table_info:
                    raise ValueError(f"Table {table_name} not found")

                # Get row count
                count_sql = f"SELECT COUNT(*) as row_count FROM {table_name}"
                row_count = session.execute(text(count_sql)).scalar()

                # Get table size
                size_sql = f"""
                SELECT 
                    pg_size_pretty(pg_total_relation_size('{table_name}')) as total_size,
                    pg_size_pretty(pg_relation_size('{table_name}')) as table_size,
                    pg_size_pretty(pg_total_relation_size('{table_name}') - pg_relation_size('{table_name}')) as index_size
                """

                size_info = session.execute(text(size_sql)).fetchone()

                # Get column information
                columns_sql = f"""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns 
                WHERE table_name = :table_name
                ORDER BY ordinal_position
                """

                columns = session.execute(
                    text(columns_sql), {"table_name": table_name}
                ).fetchall()

                return {
                    "table_name": table_name,
                    "schema": table_info.schemaname,
                    "owner": table_info.tableowner,
                    "row_count": row_count,
                    "total_size": size_info.total_size,
                    "table_size": size_info.table_size,
                    "index_size": size_info.index_size,
                    "has_indexes": table_info.hasindexes,
                    "has_rules": table_info.hasrules,
                    "has_triggers": table_info.hastriggers,
                    "columns": [
                        {
                            "name": col.column_name,
                            "type": col.data_type,
                            "nullable": col.is_nullable == "YES",
                            "default": col.column_default,
                        }
                        for col in columns
                    ],
                }

        except Exception as e:
            logger.error(
                "Failed to get table statistics", table=table_name, error=str(e)
            )
            raise


class CRUDOperations(Generic[T]):
    """Generic CRUD operations for Pydantic models."""

    def __init__(
        self, db_manager: DatabaseManager, table_name: str, model_class: Type[T]
    ):
        self.db = db_manager
        self.table_name = table_name
        self.model_class = model_class

    def create(self, obj: BaseModel) -> T:
        """Create a new record."""
        try:
            data = obj.model_dump(exclude_unset=True)
            client = self.db.get_supabase_client()
            response = client.table(self.table_name).insert(data).execute()

            if response.data:
                return self.model_class.model_validate(response.data[0])
            else:
                raise ValueError("Create operation returned no data")

        except Exception as e:
            logger.error("Failed to create record", table=self.table_name, error=str(e))
            raise

    def get_by_id(self, record_id: Union[str, UUID]) -> Optional[T]:
        """Get record by ID."""
        try:
            data = self.db.get_record_by_id(self.table_name, record_id)
            return self.model_class.model_validate(data) if data else None
        except Exception as e:
            logger.error(
                "Failed to get record by ID",
                table=self.table_name,
                record_id=str(record_id),
                error=str(e),
            )
            raise

    def get_many(
        self,
        filters: Optional[Dict] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[T]:
        """Get multiple records with filtering."""
        try:
            data = self.db.get_records_by_filter(
                self.table_name, filters or {}, limit, order_by
            )
            return [self.model_class.model_validate(item) for item in data]
        except Exception as e:
            logger.error(
                "Failed to get records",
                table=self.table_name,
                filters=filters,
                error=str(e),
            )
            raise

    def update(self, record_id: Union[str, UUID], updates: Dict) -> Optional[T]:
        """Update a record."""
        try:
            data = self.db.update_record(self.table_name, record_id, updates)
            return self.model_class.model_validate(data) if data else None
        except Exception as e:
            logger.error(
                "Failed to update record",
                table=self.table_name,
                record_id=str(record_id),
                error=str(e),
            )
            raise

    def delete(self, record_id: Union[str, UUID]) -> bool:
        """Delete a record."""
        return self.db.delete_record(self.table_name, record_id)

    def count(self, filters: Optional[Dict] = None) -> int:
        """Count records."""
        return self.db.count_records(self.table_name, filters)


# Global database manager instance
db_manager = DatabaseManager()


def get_database_manager() -> DatabaseManager:
    """Get the global DatabaseManager instance."""
    return db_manager


def get_supabase_client() -> Client:
    """Get Supabase client instance."""
    return db_manager.get_supabase_client()


@contextmanager
def get_db_session():
    """Get a database session context manager."""
    with db_manager.get_session() as session:
        yield session


def test_database_connection() -> bool:
    """Test database connectivity."""
    return db_manager.test_connection()
