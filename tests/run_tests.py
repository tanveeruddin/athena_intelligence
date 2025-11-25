#!/usr/bin/env python3
"""
Test runner for ASX Announcement Scraper A2A System.
Runs all tests and generates coverage reports.
"""

import sys
import subprocess
from pathlib import Path


def run_tests(verbose=False, coverage=False):
    """
    Run all tests.

    Args:
        verbose: Enable verbose output
        coverage: Generate coverage report
    """
    # Base pytest command
    cmd = ["pytest", "tests/"]

    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")

    if coverage:
        cmd.extend(["--cov=.", "--cov-report=html", "--cov-report=term"])

    print("="*70)
    print("Running ASX Scraper A2A Tests")
    print("="*70)
    print(f"Command: {' '.join(cmd)}\n")

    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "="*70)
        print("✅ All tests passed!")
        print("="*70)

        if coverage:
            print("\n📊 Coverage report generated in htmlcov/index.html")
    else:
        print("\n" + "="*70)
        print("❌ Some tests failed")
        print("="*70)

    return result.returncode


def run_specific_test(test_path):
    """Run a specific test file or function."""
    cmd = ["pytest", test_path, "-v"]

    print(f"Running: {test_path}")
    result = subprocess.run(cmd)
    return result.returncode


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run tests for ASX Scraper A2A")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-c", "--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("-t", "--test", type=str, help="Run specific test (e.g., tests/test_models.py::TestCompany)")
    parser.add_argument("--models", action="store_true", help="Run only model tests")
    parser.add_argument("--a2a", action="store_true", help="Run only A2A protocol tests")

    args = parser.parse_args()

    if args.test:
        return run_specific_test(args.test)
    elif args.models:
        return run_specific_test("tests/test_models.py")
    elif args.a2a:
        return run_specific_test("tests/test_a2a.py")
    else:
        return run_tests(verbose=args.verbose, coverage=args.coverage)


if __name__ == "__main__":
    sys.exit(main())
