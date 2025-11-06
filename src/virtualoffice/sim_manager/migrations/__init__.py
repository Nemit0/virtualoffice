"""
Database migrations for Communication Diversity feature.

This package contains SQL migration scripts and a migration runner.
"""

from .run_migrations import run_migrations, verify_migrations

__all__ = ['run_migrations', 'verify_migrations']
