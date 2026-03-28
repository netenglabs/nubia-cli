#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#

import unittest
from nubia.internal.helpers import matches_choice_pattern


class PatternMatchingTest(unittest.TestCase):
    """Test cases for pattern matching functionality in choice validation."""

    def test_literal_matching(self):
        """Test basic literal string matching."""
        choices = ['a', 'a1', 'b1', 'a2a1']

        # Should match exact literals
        self.assertTrue(matches_choice_pattern('a', choices))
        self.assertTrue(matches_choice_pattern('a1', choices))
        self.assertTrue(matches_choice_pattern('b1', choices))
        self.assertTrue(matches_choice_pattern('a2a1', choices))

        # Should not match non-existent literals
        self.assertFalse(matches_choice_pattern('c', choices))
        self.assertFalse(matches_choice_pattern('a2', choices))

    def test_negation_matching(self):
        """Test negation patterns (!pattern)."""
        choices = ['a', 'a1', 'b1', 'a2a1']

        # Should match literal choices
        self.assertTrue(matches_choice_pattern('a', choices))
        self.assertTrue(matches_choice_pattern('a1', choices))
        self.assertTrue(matches_choice_pattern('b1', choices))
        self.assertTrue(matches_choice_pattern('a2a1', choices))

        # Should accept negation patterns if the negated choice exists
        self.assertTrue(matches_choice_pattern(
            '!a1', choices))  # a1 exists in choices
        self.assertTrue(matches_choice_pattern(
            '!b1', choices))  # b1 exists in choices

        # Should reject negation patterns if the negated choice doesn't exist
        self.assertFalse(matches_choice_pattern('!c', choices)
                         )  # c doesn't exist in choices

        # Should not match non-existent literal choices
        self.assertFalse(matches_choice_pattern('c', choices))

    def test_regex_matching(self):
        """Test regex patterns (~pattern)."""
        choices = ['a', 'a1', 'b1', 'a2a1']

        # Should match literal choices
        self.assertTrue(matches_choice_pattern('a', choices))
        self.assertTrue(matches_choice_pattern('a1', choices))
        self.assertTrue(matches_choice_pattern('a2a1', choices))
        self.assertTrue(matches_choice_pattern('b1', choices))

        # Should accept valid regex patterns
        self.assertTrue(matches_choice_pattern('~a.*', choices))  # valid regex
        self.assertTrue(matches_choice_pattern('~b.*', choices))  # valid regex
        self.assertTrue(matches_choice_pattern('~.*', choices))   # valid regex

        # Should reject invalid regex patterns
        self.assertFalse(matches_choice_pattern(
            '~[invalid', choices))  # invalid regex
        self.assertFalse(matches_choice_pattern('~(', choices))  # invalid regex

        # Should not match non-existent literal choices
        self.assertFalse(matches_choice_pattern('c', choices))

    def test_negated_regex_matching(self):
        """Test negated regex patterns (!~pattern)."""
        choices = ['a', 'a1', 'b1', 'a2a1']

        # Should match literal choices
        self.assertTrue(matches_choice_pattern('a', choices))
        self.assertTrue(matches_choice_pattern('a1', choices))
        self.assertTrue(matches_choice_pattern('b1', choices))
        self.assertTrue(matches_choice_pattern('a2a1', choices))

        # Should accept valid negated regex patterns
        self.assertTrue(matches_choice_pattern('!~a.*', choices))  # valid regex
        self.assertTrue(matches_choice_pattern('!~b.*', choices))  # valid regex
        self.assertTrue(matches_choice_pattern('!~.*', choices))   # valid regex

        # Should reject invalid negated regex patterns
        self.assertFalse(matches_choice_pattern(
            '!~[invalid', choices))  # invalid regex
        self.assertFalse(matches_choice_pattern(
            '!~(', choices))  # invalid regex

        # Should not match non-existent literal choices
        self.assertFalse(matches_choice_pattern('c', choices))

    def test_mixed_patterns(self):
        """Test mixed patterns with literals, negation, and regex."""
        choices = ['a', 'a1', 'b1', 'c1', 'd1']

        # Should match literal choices
        self.assertTrue(matches_choice_pattern('a', choices))
        self.assertTrue(matches_choice_pattern('a1', choices))
        self.assertTrue(matches_choice_pattern('b1', choices))
        self.assertTrue(matches_choice_pattern('c1', choices))
        self.assertTrue(matches_choice_pattern('d1', choices))

        # Should accept valid patterns
        # negation of existing choice
        self.assertTrue(matches_choice_pattern('!a1', choices))
        self.assertTrue(matches_choice_pattern('~b.*', choices))  # valid regex
        self.assertTrue(matches_choice_pattern(
            '!~c.*', choices))  # valid negated regex

        # Should reject invalid patterns
        self.assertFalse(matches_choice_pattern('!e', choices)
                         )  # negation of non-existent choice
        self.assertFalse(matches_choice_pattern(
            '~[invalid', choices))  # invalid regex
        self.assertFalse(matches_choice_pattern(
            '!~[invalid', choices))  # invalid negated regex

        # Should not match non-existent literal choices
        self.assertFalse(matches_choice_pattern('e', choices))

    def test_invalid_regex_handling(self):
        """Test handling of invalid regex patterns."""
        choices = ['a', 'b1']

        # Should match literal choices
        self.assertTrue(matches_choice_pattern('a', choices))
        self.assertTrue(matches_choice_pattern('b1', choices))

        # Should reject invalid regex patterns
        self.assertFalse(matches_choice_pattern(
            '~[invalid', choices))  # invalid regex
        self.assertFalse(matches_choice_pattern(
            '!~[invalid', choices))  # invalid negated regex

        # Should not match non-existent patterns
        self.assertFalse(matches_choice_pattern('c', choices))

    def test_empty_choices(self):
        """Test behavior with empty choices list."""
        choices = []

        # Should not match anything with empty choices
        self.assertFalse(matches_choice_pattern('a', choices))
        self.assertFalse(matches_choice_pattern('anything', choices))

    def test_string_conversion(self):
        """Test that non-string values are converted to strings."""
        choices = [1, '2', 3.0]

        # Should convert values to strings for matching
        self.assertTrue(matches_choice_pattern('1', choices))
        self.assertTrue(matches_choice_pattern('2', choices))
        self.assertTrue(matches_choice_pattern('3.0', choices))

        # Should not match non-existent values
        self.assertFalse(matches_choice_pattern('4', choices))


if __name__ == '__main__':
    unittest.main()
