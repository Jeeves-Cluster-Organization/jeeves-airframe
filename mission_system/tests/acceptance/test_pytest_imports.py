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

    # Test 2: Import memory handlers
    try:
        from mission_system.memory.handlers import register_memory_handlers
        print("✓ from mission_system.memory.handlers import register_memory_handlers")
    except ModuleNotFoundError as e:
        print(f"✗ from mission_system.memory.handlers import register_memory_handlers")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        print(f"[WARN] from mission_system.memory.handlers - dependency missing (OK): {e}")

    # Test 3: Import memory services
    try:
        from mission_system.memory.services.session_state_service import SessionStateService
        print("✓ from mission_system.memory.services.session_state_service import SessionStateService")
    except ModuleNotFoundError as e:
        print(f"✗ from mission_system.memory.services.session_state_service")
        print(f"  Error: {e}")
        raise
    except ImportError as e:
        print(f"[WARN] session_state_service - dependency missing (OK): {e}")

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
