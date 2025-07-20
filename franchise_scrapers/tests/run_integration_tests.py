#!/usr/bin/env python3
"""Quick runner for franchise_scrapers integration tests."""

import sys
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def run_tests(test_type="mock", verbose=False):
    """Run integration tests.
    
    Args:
        test_type: "mock", "live", or "all"
        verbose: Enable verbose output
    """
    cmd = ["python", "-m", "pytest", "franchise_scrapers/tests/integration/"]
    
    if test_type == "mock":
        cmd.extend(["-m", "mock"])
    elif test_type == "live":
        cmd.extend(["--live", "-m", "live", "--timeout=300"])
    # "all" runs everything
    
    if verbose:
        cmd.append("-v")
    
    # Add color output
    cmd.append("--color=yes")
    
    print(f"Running {test_type} integration tests...")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 50)
    
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run franchise_scrapers integration tests")
    parser.add_argument(
        "--type",
        choices=["mock", "live", "all"],
        default="mock",
        help="Type of tests to run (default: mock)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--specific",
        help="Run specific test file (e.g., test_mn_flow.py)"
    )
    
    args = parser.parse_args()
    
    if args.specific:
        # Run specific test file
        cmd = ["python", "-m", "pytest", f"franchise_scrapers/tests/integration/{args.specific}"]
        if args.type == "live":
            cmd.extend(["--live", "-m", "live"])
        elif args.type == "mock":
            cmd.extend(["-m", "mock"])
        if args.verbose:
            cmd.append("-v")
        cmd.append("--color=yes")
        
        print(f"Running {args.specific}...")
        result = subprocess.run(cmd, cwd=project_root)
        sys.exit(result.returncode)
    
    # Run all tests of specified type
    sys.exit(run_tests(args.type, args.verbose))


if __name__ == "__main__":
    main()