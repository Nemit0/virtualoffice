"""
Database Migration Runner

This script applies database migrations for the Communication Diversity feature.
Migrations are applied in order and are idempotent (safe to run multiple times).

Usage:
    python -m virtualoffice.sim_manager.migrations.run_migrations
"""

import logging
from pathlib import Path
from virtualoffice.common.db import get_connection, execute_script

logger = logging.getLogger(__name__)


def run_migrations():
    """
    Run all database migrations for Communication Diversity feature.
    
    Migrations are applied in order:
    1. 001_add_inbox_messages.sql - Inbox tracking for threading
    2. 002_add_participation_stats.sql - Participation balancing
    3. 003_add_communication_generation_log.sql - Observability logging
    
    All migrations use CREATE TABLE IF NOT EXISTS, so they are safe to run
    multiple times.
    """
    migrations_dir = Path(__file__).parent
    
    migrations = [
        '001_add_inbox_messages.sql',
        '002_add_participation_stats.sql',
        '003_add_communication_generation_log.sql'
    ]
    
    logger.info("Starting database migrations for Communication Diversity feature")
    
    for migration_file in migrations:
        migration_path = migrations_dir / migration_file
        
        if not migration_path.exists():
            logger.error(f"Migration file not found: {migration_file}")
            continue
        
        logger.info(f"Applying migration: {migration_file}")
        
        try:
            with open(migration_path, 'r', encoding='utf-8') as f:
                sql = f.read()
            
            execute_script(sql)
            logger.info(f"Successfully applied migration: {migration_file}")
            
        except Exception as e:
            logger.error(f"Failed to apply migration {migration_file}: {e}")
            raise
    
    logger.info("All migrations completed successfully")


def verify_migrations():
    """
    Verify that all migration tables exist in the database.
    
    Returns:
        bool: True if all tables exist, False otherwise
    """
    required_tables = [
        'inbox_messages',
        'participation_stats',
        'communication_generation_log'
    ]
    
    try:
        with get_connection() as conn:
            for table_name in required_tables:
                result = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,)
                ).fetchone()
                
                if result:
                    logger.info(f"✓ Table '{table_name}' exists")
                else:
                    logger.error(f"✗ Table '{table_name}' does not exist")
                    return False
        
        logger.info("All migration tables verified successfully")
        return True
        
    except Exception as e:
        logger.error(f"Failed to verify migrations: {e}")
        return False


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("Communication Diversity - Database Migration Runner")
    print("=" * 60)
    print()
    
    # Run migrations
    run_migrations()
    print()
    
    # Verify migrations
    print("Verifying migrations...")
    if verify_migrations():
        print()
        print("✓ All migrations completed and verified successfully!")
    else:
        print()
        print("✗ Migration verification failed. Please check the logs.")
        exit(1)
