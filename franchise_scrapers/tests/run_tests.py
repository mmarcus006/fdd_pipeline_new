#!/usr/bin/env python3
"""Test runner for franchise_scrapers unit tests."""

import sys
import subprocess
from pathlib import Path


def run_tests():
    """Run all unit tests with pytest."""
    # Get the directory containing this script
    test_dir = Path(__file__).parent
    unit_test_dir = test_dir / "unit"
    
    # Base pytest command
    cmd = [
        sys.executable, "-m", "pytest",
        str(unit_test_dir),
        "-v",  # Verbose output
        "--tb=short",  # Short traceback format
        "-x",  # Stop on first failure
    ]
    
    # Add coverage if available
    try:
        import coverage
        cmd.extend(["--cov=franchise_scrapers", "--cov-report=term-missing"])
    except ImportError:
        print("Coverage not installed. Run 'pip install pytest-cov' for coverage reports.")
    
    # Run specific test file if provided
    if len(sys.argv) > 1:
        test_file = sys.argv[1]
        if not test_file.startswith("test_"):
            test_file = f"test_{test_file}"
        if not test_file.endswith(".py"):
            test_file = f"{test_file}.py"
        
        test_path = unit_test_dir / test_file
        if test_path.exists():
            cmd = [
                sys.executable, "-m", "pytest",
                str(test_path),
                "-v",
                "--tb=short",
            ]
        else:
            print(f"Test file not found: {test_path}")
            return 1
    
    # Run the tests
    print(f"Running command: {' '.join(cmd)}")
    print("-" * 80)
    
    result = subprocess.run(cmd)
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests())