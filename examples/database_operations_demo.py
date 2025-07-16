#!/usr/bin/env python3
"""
Demonstration of enhanced database operations layer functionality.

This script showcases the key features implemented in task 4.2:
- DatabaseManager with SQLAlchemy and connection pooling
- CRUD operations for all entity types
- Batch insert functionality for performance optimization
- Transaction management with rollback capabilities
- Query builders for common data access patterns
- Database health checks and connection monitoring
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from datetime import datetime
from uuid import uuid4
from typing import Dict, Any, List

from utils.database import (
    DatabaseManager,
    QueryBuilder,
    BatchOperations,
    DatabaseHealthCheck,
    get_database_manager,
)
from models.franchisor import Franchisor, FranchisorCreate
from models.fdd import FDD, FDDCreate, DocumentType, ProcessingStatus


def demonstrate_basic_crud_operations():
    """Demonstrate basic CRUD operations."""
    print("=== Basic CRUD Operations Demo ===")

    db = get_database_manager()

    # Test database connection
    print("1. Testing database connection...")
    is_healthy = db.test_connection()
    print(f"   Database connection: {'✓ Healthy' if is_healthy else '✗ Failed'}")

    # Create sample data
    print("\n2. Creating sample franchisor...")
    sample_franchisor = {
        "id": str(uuid4()),
        "canonical_name": "Demo Franchise Corp",
        "parent_company": "Demo Holdings LLC",
        "website": "https://demo-franchise.com",
        "phone": "(555) 123-4567",
        "email": "info@demo-franchise.com",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    try:
        # Insert record
        inserted_count = db.execute_batch_insert("franchisors", [sample_franchisor])
        print(f"   Inserted {inserted_count} franchisor record")

        # Read record
        found_record = db.get_record_by_id("franchisors", sample_franchisor["id"])
        if found_record:
            print(f"   Found franchisor: {found_record['canonical_name']}")

        # Update record
        updates = {"canonical_name": "Updated Demo Franchise Corp"}
        updated_record = db.update_record(
            "franchisors", sample_franchisor["id"], updates
        )
        if updated_record:
            print(f"   Updated franchisor name to: {updated_record['canonical_name']}")

        # Count records
        total_count = db.count_records("franchisors")
        print(f"   Total franchisors in database: {total_count}")

        # Delete record (cleanup)
        deleted = db.delete_record("franchisors", sample_franchisor["id"])
        print(f"   Cleanup: {'✓ Deleted' if deleted else '✗ Failed to delete'}")

    except Exception as e:
        print(f"   Error during CRUD operations: {e}")


def demonstrate_query_builder():
    """Demonstrate advanced query builder functionality."""
    print("\n=== Query Builder Demo ===")

    db = get_database_manager()
    query_builder = db.query()

    # Build a complex query
    print("1. Building complex query...")
    sql, params = (
        query_builder.table("franchisors")
        .select("id", "canonical_name", "created_at")
        .where("canonical_name", "ILIKE", "%franchise%")
        .where_null("deleted_at", True)
        .join("fdds", "fdds.franchise_id = franchisors.id", "left")
        .order_by("created_at", "desc")
        .limit(10)
        .build_sql()
    )

    print(f"   Generated SQL: {sql}")
    print(f"   Parameters: {params}")

    # Demonstrate different query patterns
    print("\n2. Different query patterns...")

    # Simple filter query
    simple_query = db.query().table("franchisors").where("canonical_name", "=", "Test")
    sql, params = simple_query.build_sql()
    print(f"   Simple filter: {sql}")

    # Range query
    range_query = (
        db.query()
        .table("fdds")
        .where_between("issue_date", "2024-01-01", "2024-12-31")
        .where_in("processing_status", ["pending", "processing"])
    )
    sql, params = range_query.build_sql()
    print(f"   Range query: {sql}")

    # Count query
    count_query = (
        db.query().table("franchisors").where("canonical_name", "ILIKE", "%corp%")
    )
    sql, params = count_query.build_sql()
    print(f"   Count query base: {sql}")


def demonstrate_batch_operations():
    """Demonstrate batch operations for performance."""
    print("\n=== Batch Operations Demo ===")

    db = get_database_manager()
    batch_ops = db.batch

    # Generate sample data
    print("1. Preparing sample data for batch operations...")
    sample_records = []
    for i in range(5):
        sample_records.append(
            {
                "id": str(uuid4()),
                "canonical_name": f"Batch Test Franchise {i+1}",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }
        )

    print(f"   Generated {len(sample_records)} sample records")

    try:
        # Batch insert
        print("\n2. Performing batch insert...")
        inserted_count = batch_ops.batch_insert_chunked(
            "franchisors", sample_records, chunk_size=2
        )
        print(f"   Batch inserted {inserted_count} records")

        # Batch update
        print("\n3. Performing batch update...")
        update_data = []
        for record in sample_records:
            update_data.append(
                {
                    "id": record["id"],
                    "canonical_name": f"Updated {record['canonical_name']}",
                    "updated_at": datetime.now().isoformat(),
                }
            )

        updated_count = batch_ops.batch_update_by_ids("franchisors", update_data)
        print(f"   Batch updated {updated_count} records")

        # Batch delete (cleanup)
        print("\n4. Performing batch delete (cleanup)...")
        record_ids = [record["id"] for record in sample_records]
        deleted_count = batch_ops.batch_delete_by_ids("franchisors", record_ids)
        print(f"   Batch deleted {deleted_count} records")

    except Exception as e:
        print(f"   Error during batch operations: {e}")


def demonstrate_health_monitoring():
    """Demonstrate database health monitoring."""
    print("\n=== Health Monitoring Demo ===")

    db = get_database_manager()
    health_check = db.health_check

    # Comprehensive health check
    print("1. Performing comprehensive health check...")
    health_status = health_check.check_connection()

    print(
        f"   Overall health: {'✓ Healthy' if health_status['healthy'] else '✗ Unhealthy'}"
    )
    print(f"   Response time: {health_status['response_time_ms']}ms")
    print(
        f"   Supabase connection: {'✓' if health_status['supabase_connection'] else '✗'}"
    )
    print(
        f"   SQLAlchemy connection: {'✓' if health_status['sqlalchemy_connection'] else '✗'}"
    )

    if health_status["pool_status"]:
        pool = health_status["pool_status"]
        print(
            f"   Connection pool - Size: {pool.get('size', 'N/A')}, Active: {pool.get('checked_out', 'N/A')}"
        )

    if health_status["error"]:
        print(f"   Error: {health_status['error']}")

    # Check table existence
    print("\n2. Checking table existence...")
    tables_to_check = ["franchisors", "fdds", "fdd_sections", "nonexistent_table"]
    for table in tables_to_check:
        exists = health_check.check_table_exists(table)
        print(f"   Table '{table}': {'✓ Exists' if exists else '✗ Not found'}")

    # Connection pool status
    print("\n3. Connection pool status...")
    try:
        pool_status = db.get_connection_pool_status()
        if pool_status:
            print(f"   Pool size: {pool_status.get('pool_size', 'N/A')}")
            print(
                f"   Available connections: {pool_status.get('available_connections', 'N/A')}"
            )
            print(
                f"   Active connections: {pool_status.get('active_connections', 'N/A')}"
            )
            print(
                f"   Total connections: {pool_status.get('total_connections', 'N/A')}"
            )
        else:
            print("   Pool status not available")
    except Exception as e:
        print(f"   Error getting pool status: {e}")


def demonstrate_transaction_management():
    """Demonstrate transaction management with rollback."""
    print("\n=== Transaction Management Demo ===")

    db = get_database_manager()

    print("1. Demonstrating successful transaction...")
    try:
        with db.transaction() as session:
            # This would normally execute SQL operations
            print("   Transaction started")
            print("   Performing database operations...")
            print("   Transaction committed successfully")
    except Exception as e:
        print(f"   Transaction failed: {e}")

    print("\n2. Demonstrating transaction rollback...")
    try:
        with db.transaction() as session:
            print("   Transaction started")
            print("   Performing database operations...")
            # Simulate an error
            raise ValueError("Simulated error for rollback demonstration")
    except ValueError as e:
        print(f"   Transaction rolled back due to error: {e}")
    except Exception as e:
        print(f"   Unexpected error: {e}")

    print("\n3. Demonstrating retry mechanism...")

    def sample_operations(session):
        """Sample database operations for retry demo."""
        print("   Executing sample operations...")
        return "Operations completed successfully"

    try:
        result = db.execute_transaction_with_retry(sample_operations, max_retries=2)
        print(f"   Retry result: {result}")
    except Exception as e:
        print(f"   Retry failed: {e}")


def demonstrate_advanced_features():
    """Demonstrate advanced database features."""
    print("\n=== Advanced Features Demo ===")

    db = get_database_manager()

    # Pagination
    print("1. Demonstrating pagination...")
    try:
        paginated_result = db.get_records_paginated(
            "franchisors",
            page=1,
            page_size=5,
            filters={"canonical_name": "Test%"},
            order_by="created_at",
        )

        print(f"   Page: {paginated_result['pagination']['page']}")
        print(f"   Total records: {paginated_result['pagination']['total_count']}")
        print(f"   Records on page: {len(paginated_result['records'])}")
        print(f"   Has next page: {paginated_result['pagination']['has_next']}")

    except Exception as e:
        print(f"   Pagination error: {e}")

    # Bulk operations
    print("\n2. Demonstrating bulk update by condition...")
    try:
        updated_count = db.bulk_update_by_condition(
            "franchisors",
            {"updated_at": datetime.now().isoformat()},
            {"canonical_name": "Test Franchise"},
        )
        print(f"   Bulk updated {updated_count} records")
    except Exception as e:
        print(f"   Bulk update error: {e}")

    # Table statistics
    print("\n3. Demonstrating table statistics...")
    try:
        stats = db.get_table_statistics("franchisors")
        print(f"   Table: {stats['table_name']}")
        print(f"   Schema: {stats['schema']}")
        print(f"   Row count: {stats['row_count']}")
        print(f"   Total size: {stats['total_size']}")
        print(f"   Columns: {len(stats['columns'])}")
        print(f"   Has indexes: {stats['has_indexes']}")
    except Exception as e:
        print(f"   Table statistics error: {e}")


def main():
    """Run all demonstrations."""
    print("🚀 FDD Pipeline Database Operations Layer Demo")
    print("=" * 50)

    try:
        demonstrate_basic_crud_operations()
        demonstrate_query_builder()
        demonstrate_batch_operations()
        demonstrate_health_monitoring()
        demonstrate_transaction_management()
        demonstrate_advanced_features()

        print("\n" + "=" * 50)
        print("✅ Database operations layer demonstration completed!")
        print("\nKey features implemented:")
        print("• DatabaseManager with SQLAlchemy and connection pooling")
        print("• Comprehensive CRUD operations for all entity types")
        print("• Batch insert functionality for performance optimization")
        print("• Transaction management with rollback capabilities")
        print("• Advanced query builders for common data access patterns")
        print("• Database health checks and connection monitoring")
        print("• Integration tests with comprehensive coverage")

    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
