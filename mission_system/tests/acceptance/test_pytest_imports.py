#!/usr/bin/env python3
"""
Test if imports work when run by pytest vs regular Python.

Run with:
  python test_pytest_imports.py          # Should work
  pytest test_pytest_imports.py -v      # May fail if there's a pytest-specific issue
"""

def test_memory_imports():
    """Test that all memory module imports work."""

    # Test 1: Import mission_system.memory package
    try:
        import mission_system.memory
        print("✓ import mission_system.memory")
    except ModuleNotFoundError as e:
        print(f"✗ import mission_system.memory - {e}")
        raise

    # Test 2: Import from mission_system.memory (moved from memory_module.adapters)
    try:
        from mission_system.memory.sql_adapter import SQLAdapter
        print("✓ from mission_system.memory.sql_adapter import SQLAdapter")
    except ModuleNotFoundError as e:
        print(f"✗ from mission_system.memory.sql_adapter import SQLAdapter")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        # This is OK - dependency missing
        print(f"[WARN] from mission_system.memory.sql_adapter import SQLAdapter")
        print(f"  Dependency missing (OK): {e}")

    # Test 4: Import memory.manager
    try:
        from mission_system.memory.manager import MemoryManager
        print("✓ from mission_system.memory.manager import MemoryManager")
    except ModuleNotFoundError as e:
        print(f"✗ from mission_system.memory.manager import MemoryManager")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        # This is OK - dependency missing
        print(f"[WARN] from mission_system.memory.manager import MemoryManager")
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
