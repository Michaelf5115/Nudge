"""
Migration 0001 — Enable pgvector extension.

This must run before any migration that creates a VectorField column.
The `IF NOT EXISTS` guard makes it safe to re-run (e.g. in CI environments
where the extension may already be present).
"""

from django.db import migrations


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector;",
            reverse_sql="DROP EXTENSION IF EXISTS vector;",
        ),
    ]
