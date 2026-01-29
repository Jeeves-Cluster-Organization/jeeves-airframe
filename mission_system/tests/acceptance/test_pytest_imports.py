#!/usr/bin/env python3
"""
Test if imports work when run by pytest vs regular Python.

Run with:
  python test_pytest_imports.py          # Should work
  pytest test_pytest_imports.py -v      # May fail if there's a pytest-specific issue
"""

def test_memory_imports():
    """Test that all memory module imports work."""

    # Test 1: Import memory_module package
    try:
        import memory_module
        print("✓ import memory_module")
    except ModuleNotFoundError as e:
        print(f"✗ import memory_module - {e}")
        raise

    # Test 2: Import from jeeves_infra.memory.services (moved from memory_module)
    try:
        from jeeves_infra.memory.services.embedding_service import EmbeddingService
        print("✓ from jeeves_infra.memory.services.embedding_service import EmbeddingService")
    except ModuleNotFoundError as e:
        print(f"✗ from jeeves_infra.memory.services.embedding_service import EmbeddingService")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        # This is OK - dependency missing
        print(f"[WARN] from jeeves_infra.memory.services.embedding_service import EmbeddingService")
        print(f"  Dependency missing (OK): {e}")

    # Test 3: Import from jeeves_infra.memory (moved from memory_module.adapters)
    try:
        from jeeves_infra.memory.sql_adapter import SQLAdapter
        print("✓ from jeeves_infra.memory.sql_adapter import SQLAdapter")
    except ModuleNotFoundError as e:
        print(f"✗ from jeeves_infra.memory.sql_adapter import SQLAdapter")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        # This is OK - dependency missing
        print(f"[WARN] from jeeves_infra.memory.sql_adapter import SQLAdapter")
        print(f"  Dependency missing (OK): {e}")

    # Test 4: Import memory.manager
    try:
        from memory_module.manager import MemoryManager
        print("✓ from memory_module.manager import MemoryManager")
    except ModuleNotFoundError as e:
        print(f"✗ from memory_module.manager import MemoryManager")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        # This is OK - dependency missing
        print(f"[WARN] from memory_module.manager import MemoryManager")
        print(f"  Dependency missing (OK): {e}")

    # Test 5: Import memory.intent_classifier
    try:
        from memory_module.intent_classifier import IntentClassifier
        print("✓ from memory_module.intent_classifier import IntentClassifier")
    except ModuleNotFoundError as e:
        print(f"✗ from memory_module.intent_classifier import IntentClassifier")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        # This is OK - dependency missing
        print(f"[WARN] from memory_module.intent_classifier import IntentClassifier")
        print(f"  Dependency missing (OK): {e}")

    print("\n[OK] All import paths are correct!")
    print("(Some modules may fail to fully import due to missing dependencies,")
    print(" but the MODULE PATHS are all valid)")


if __name__ == "__main__":
    # Run as a regular Python script
    print("="*70)
    print("RUNNING AS REGULAR PYTHON SCRIPT")
    print("="*70)
    test_memory_imports()
    print("\n" + "="*70)
    print("SUCCESS - Now try running with pytest:")
    print("  pytest test_pytest_imports.py -v")
    print("="*70)
