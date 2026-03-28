#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#

"""
Integration test to verify pattern matching works end-to-end with nubia.
"""

from pattern_matching_example import pattern_demo, file_demo
from tests.util import TestShell
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'example'))


class PatternMatchingIntegrationTest:
    """Integration test for pattern matching functionality."""

    async def test_pattern_matching_integration(self):
        """Test pattern matching through the full nubia framework."""
        shell = TestShell([pattern_demo, file_demo])

        print("Testing pattern matching integration with nubia...")

        # Test cases: (command, expected_result, description)
        test_cases = [
            # Valid patterns (return None or 0 for success)
            ("pattern-demo pattern=a", [0, None], "literal match 'a'"),
            ("pattern-demo pattern=a2", [0, None], "regex match '~a.*'"),
            ("pattern-demo pattern=a2a1", [0, None], "literal match 'a2a1'"),

            # Invalid patterns (should return 4 for validation error)
            ("pattern-demo pattern=a1", 4, "negated by '!a1'"),
            ("pattern-demo pattern=b1", 4, "negated by '!~b.*'"),
            ("pattern-demo pattern=c", 4, "no matching pattern"),
        ]

        all_passed = True

        for cmd, expected_result, description in test_cases:
            try:
                result = await shell.run_interactive_line(cmd)
                if isinstance(expected_result, list):
                    if result in expected_result:
                        print(f"✓ {description}: {cmd}")
                    else:
                        print(
                            f"✗ {description}: {cmd} (expected {expected_result}, got {result})")
                        all_passed = False
                else:
                    if result == expected_result:
                        print(f"✓ {description}: {cmd}")
                    else:
                        print(
                            f"✗ {description}: {cmd} (expected {expected_result}, got {result})")
                        all_passed = False
            except Exception as e:
                print(f"✗ {description}: {cmd} (exception: {e})")
                all_passed = False

        # Test file pattern matching
        file_test_cases = [
            ("file-demo files=main.py", [0, None], "regex match '~.*\\.py$'"),
            ("file-demo files=test_file.py",
             [0, None], "regex match '~test_.*'"),
            ("file-demo files=data.tmp", 4, "negated by '!~.*\\.tmp$'"),
            ("file-demo files=backup_file", 4, "negated by '!~.*_backup'"),
        ]

        print("\nTesting file pattern matching...")
        for cmd, expected_result, description in file_test_cases:
            try:
                result = await shell.run_interactive_line(cmd)
                if isinstance(expected_result, list):
                    if result in expected_result:
                        print(f"✓ {description}: {cmd}")
                    else:
                        print(
                            f"✗ {description}: {cmd} (expected {expected_result}, got {result})")
                        all_passed = False
                else:
                    if result == expected_result:
                        print(f"✓ {description}: {cmd}")
                    else:
                        print(
                            f"✗ {description}: {cmd} (expected {expected_result}, got {result})")
                        all_passed = False
            except Exception as e:
                print(f"✗ {description}: {cmd} (exception: {e})")
                all_passed = False

        return all_passed


async def main():
    """Run the integration test."""
    test = PatternMatchingIntegrationTest()
    success = await test.test_pattern_matching_integration()

    if success:
        print("\n🎉 All pattern matching integration tests passed!")
        return 0
    else:
        print("\n❌ Some pattern matching integration tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
