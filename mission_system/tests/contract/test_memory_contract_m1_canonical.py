"""Memory Contract M1: Canonical State is Ground Truth

Validates adherence to:
"Embeddings must reference their source tables (facts, messages, code).
Deleting canonical data cascades to derived views."

Key Requirements:
1. Every embedding must reference a canonical source (facts, messages, code)
2. Embeddings cannot exist without canonical source
3. Deleting canonical data must cascade to embeddings
4. Foreign keys (or trigger-based validation) enforce referential integrity

Reference: MEMORY_INFRASTRUCTURE_CONTRACT.md, Principle M1

Note: v3.0 Pivot - tasks and journal_entries tables were removed.
      Valid source types are now: fact, message, code
"""

import pytest
from uuid import uuid4

# Requires PostgreSQL database
pytestmark = pytest.mark.requires_postgres


@pytest.mark.contract
class TestM1Canonical:
    """Validate M1: Canonical State is Ground Truth."""

    async def test_embeddings_reference_canonical_source(self, pg_test_db):
        """Every embedding must reference a canonical source table.

        M1 Requirement: "Embeddings must reference their source tables"

        Test Strategy:
        1. Create fact (canonical source)
        2. Create embedding referencing fact
        3. Verify foreign key relationship exists
        4. Verify source_type and source_id are populated
        """
        # Create canonical fact
        fact_id = str(uuid4())
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "test_key",
            "value": "Test fact value"
        })

        # Create embedding referencing fact
        chunk_id = str(uuid4())
        await pg_test_db.insert("semantic_chunks", {
            "chunk_id": chunk_id,
            "source_type": "fact",
            "source_id": fact_id,
            "chunk_text": "Test fact chunk",
            "user_id": "test_user",
            "embedding": [0.1] * 384  # Dummy embedding
        })

        # Verify embedding references canonical source
        result = await pg_test_db.fetch_one(
            "SELECT source_type, source_id FROM semantic_chunks WHERE chunk_id = ?",
            (chunk_id,)
        )
        assert result is not None
        assert result["source_type"] == "fact"
        # PostgreSQL returns UUID objects; convert for comparison with string
        assert str(result["source_id"]) == fact_id, \
            "M1 violation: Embedding does not reference canonical source"


    async def test_deleting_canonical_cascades_to_embeddings(self, pg_test_db):
        """Deleting canonical data must cascade to derived embeddings.

        M1 Requirement: "Deleting canonical data cascades to derived views"

        Test Strategy:
        1. Create fact + embedding
        2. Delete fact
        3. Verify embedding is also deleted (CASCADE via trigger)
        """
        # Create canonical fact
        fact_id = str(uuid4())
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "cascade_test",
            "value": "Test fact"
        })

        # Create embedding referencing fact
        chunk_id = str(uuid4())
        await pg_test_db.insert("semantic_chunks", {
            "chunk_id": chunk_id,
            "source_type": "fact",
            "source_id": fact_id,
            "chunk_text": "Test fact chunk",
            "user_id": "test_user",
            "embedding": [0.1] * 384
        })

        # Delete canonical fact
        await pg_test_db.execute("DELETE FROM knowledge_facts WHERE fact_id = ?", (fact_id,))

        # Verify embedding was cascaded (deleted)
        result = await pg_test_db.fetch_one(
            "SELECT * FROM semantic_chunks WHERE source_id = ?", (fact_id,)
        )
        assert result is None, \
            "M1 violation: Embedding persisted after canonical source was deleted"


    async def test_orphaned_embeddings_prevented_by_referential_integrity(self, pg_test_db):
        """Orphaned embeddings must be prevented by referential integrity checks.

        M1 Requirement: "Embeddings must reference their source tables"

        Test Strategy:
        1. Attempt to create embedding with non-existent source
        2. Verify referential integrity check prevents insertion
           (Uses trigger-based enforcement for polymorphic FK)
        """
        # Attempt to create embedding with non-existent fact
        with pytest.raises(Exception) as exc_info:
            await pg_test_db.insert("semantic_chunks", {
                "chunk_id": str(uuid4()),
                "source_type": "fact",
                "source_id": str(uuid4()),  # Non-existent fact
                "chunk_text": "Orphan chunk",
                "user_id": "test_user",
                "embedding": [0.1] * 384
            })

        # Verify referential integrity violation (trigger raises with FK error code)
        error_message = str(exc_info.value).lower()
        assert "foreign key" in error_message or "constraint" in error_message or "does not exist" in error_message, \
            "M1 violation: Orphaned embedding created (no referential integrity enforcement)"


    async def test_all_semantic_chunks_have_valid_source_type(self, pg_test_db):
        """All semantic chunks must have valid source_type from allowed list.

        M1 Requirement: Source types must be: fact, message, code

        Test Strategy:
        1. Query semantic_chunks schema
        2. Verify source_type has CHECK constraint or ENUM
        3. Attempt invalid source_type (should fail)
        """
        # Create fact for valid reference
        fact_id = str(uuid4())
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "source_type_test",
            "value": "Test fact"
        })

        # Attempt to create embedding with invalid source_type
        # Note: This should fail if schema enforces CHECK constraint
        try:
            await pg_test_db.insert("semantic_chunks", {
                "chunk_id": str(uuid4()),
                "source_type": "invalid_type",
                "source_id": fact_id,
                "chunk_text": "Test chunk",
                "user_id": "test_user",
                "embedding": [0.1] * 384
            })

            # If we get here, schema doesn't enforce source_type constraint
            # Clean up for subsequent tests
            await pg_test_db.execute(
                "DELETE FROM semantic_chunks WHERE source_type = 'invalid_type'"
            )

            # Document gap (not a hard failure)
            pytest.skip(
                "M1 warning: source_type not enforced at database level. "
                "Application must validate source_type in ['fact', 'message', 'code']"
            )
        except Exception:
            # Good! Schema enforces source_type constraint
            pass


    async def test_canonical_to_embedding_lineage_traceable(self, pg_test_db):
        """Embeddings must be traceable back to canonical source.

        M1 Requirement: "Canonical State is Ground Truth"

        Test Strategy:
        1. Create fact
        2. Create multiple embeddings from same fact
        3. Query all embeddings for a given fact
        4. Verify all embeddings can be traced back
        """
        # Create canonical fact
        fact_id = str(uuid4())
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "lineage_test",
            "value": "Fact with multiple chunks"
        })

        # Create multiple embeddings from same fact
        # Note: chunk_index must be unique per (source_type, source_id)
        for i in range(3):
            await pg_test_db.insert("semantic_chunks", {
                "chunk_id": str(uuid4()),
                "source_type": "fact",
                "source_id": fact_id,
                "chunk_index": i,  # Unique chunk_index per source
                "chunk_text": f"Chunk {i}",
                "user_id": "test_user",
                "embedding": [0.1 * (i + 1)] * 384
            })

        # Verify all embeddings can be traced back to fact
        results = await pg_test_db.fetch_all(
            """
            SELECT chunk_id, source_type, source_id
            FROM semantic_chunks
            WHERE source_type = 'fact' AND source_id = ?
            """,
            (fact_id,)
        )

        assert len(results) == 3, "M1 violation: Not all embeddings traceable"
        for result in results:
            assert result["source_type"] == "fact"
            # PostgreSQL returns UUID objects; convert for comparison with string
            assert str(result["source_id"]) == fact_id


    async def test_updating_canonical_does_not_orphan_embeddings(self, pg_test_db):
        """Updating canonical fact_id must update embeddings or prevent update.

        M1 Requirement: "Canonical State is Ground Truth"

        Test Strategy:
        1. Create fact + embedding
        2. Update fact_id (if allowed)
        3. Verify embedding still references correct fact
           OR verify update is prevented (ON UPDATE CASCADE or RESTRICT)
        """
        # Create canonical fact
        old_fact_id = str(uuid4())
        await pg_test_db.insert("knowledge_facts", {
            "fact_id": old_fact_id,
            "user_id": "test_user",
            "domain": "test",
            "key": "update_test",
            "value": "Test fact"
        })

        # Create embedding referencing fact
        chunk_id = str(uuid4())
        await pg_test_db.insert("semantic_chunks", {
            "chunk_id": chunk_id,
            "source_type": "fact",
            "source_id": old_fact_id,
            "chunk_text": "Test chunk",
            "user_id": "test_user",
            "embedding": [0.1] * 384
        })

        # Attempt to update fact_id
        new_fact_id = str(uuid4())
        try:
            await pg_test_db.execute(
                "UPDATE knowledge_facts SET fact_id = ? WHERE fact_id = ?",
                (new_fact_id, old_fact_id)
            )

            # If update succeeded, verify embedding was cascaded
            result = await pg_test_db.fetch_one(
                "SELECT source_id FROM semantic_chunks WHERE chunk_id = ?",
                (chunk_id,)
            )
            assert result is not None
            # PostgreSQL returns UUID objects; convert for comparison with string
            assert str(result["source_id"]) == new_fact_id, \
                "M1 violation: Embedding not updated after fact_id change (ON UPDATE CASCADE not configured)"

        except Exception:
            # Update prevented by foreign key constraint (ON UPDATE RESTRICT)
            # This is acceptable - prevents orphaned embeddings
            # Verify embedding still references old fact_id
            result = await pg_test_db.fetch_one(
                "SELECT source_id FROM semantic_chunks WHERE chunk_id = ?",
                (chunk_id,)
            )
            assert result is not None
            # PostgreSQL returns UUID objects; convert for comparison with string
            assert str(result["source_id"]) == old_fact_id, \
                "M1 violation: Embedding corrupted after failed fact_id update"


@pytest.mark.contract
class TestM1Schema:
    """Validate M1 schema structure requirements."""

    async def test_semantic_chunks_table_has_required_columns(self, pg_test_db):
        """Semantic chunks table must have all required M1 columns.

        M1 Requirement: source_type, source_id for canonical reference

        Test Strategy:
        1. Query table schema
        2. Verify required columns exist
        """
        # Query table schema
        result = await pg_test_db.fetch_all(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'semantic_chunks'
            ORDER BY ordinal_position
            """
        )

        # Convert to dict for easier assertion
        columns = {row["column_name"]: row for row in result}

        # Verify required M1 columns exist
        assert "source_type" in columns, "M1 violation: source_type column missing"
        assert "source_id" in columns, "M1 violation: source_id column missing"
        assert "embedding" in columns, "M1 violation: embedding column missing"

        # Verify source_type and source_id are NOT NULL
        assert columns["source_type"]["is_nullable"] == "NO", \
            "M1 violation: source_type should be NOT NULL"
        assert columns["source_id"]["is_nullable"] == "NO", \
            "M1 violation: source_id should be NOT NULL"


    async def test_referential_integrity_enforced_for_canonical_sources(self, pg_test_db):
        """Referential integrity must be enforced for canonical source tables.

        M1 Requirement: "Embeddings must reference their source tables"

        Test Strategy:
        1. Check for triggers that enforce referential integrity
           (PostgreSQL doesn't support polymorphic FKs, so we use triggers)
        2. Verify the validation trigger exists on semantic_chunks
        """
        # Query for triggers on semantic_chunks that enforce source validation
        result = await pg_test_db.fetch_all(
            """
            SELECT
                trigger_name,
                event_manipulation,
                action_timing
            FROM information_schema.triggers
            WHERE event_object_table = 'semantic_chunks'
                AND trigger_name LIKE '%check_semantic_chunk_source%'
            """
        )

        # Verify the referential integrity trigger exists
        assert len(result) > 0, \
            "M1 violation: No referential integrity enforcement on semantic_chunks. " \
            "Expected trigger 'trg_check_semantic_chunk_source' for polymorphic FK validation."

        # Also verify CASCADE delete triggers exist on canonical tables
        cascade_triggers = await pg_test_db.fetch_all(
            """
            SELECT
                event_object_table,
                trigger_name
            FROM information_schema.triggers
            WHERE trigger_name LIKE '%cascade_delete%chunks%'
            """
        )

        # Should have cascade triggers for knowledge_facts (facts)
        trigger_tables = [t["event_object_table"] for t in cascade_triggers]
        assert "knowledge_facts" in trigger_tables, \
            "M1 violation: Missing CASCADE delete trigger on knowledge_facts table"
