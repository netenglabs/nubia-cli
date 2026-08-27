#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#

import logging
import threading
import unittest
import warnings

from nubia.internal.io.logger import ContextFilter


class ContextFilterTest(unittest.TestCase):
    def test_filter_at_debug_level_does_not_warn(self):
        """ContextFilter must not raise a DeprecationWarning when
        computing the optional thread-name field at DEBUG level."""
        record = logging.LogRecord(
            name="nubia.test",
            level=logging.DEBUG,
            pathname=__file__,
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            ContextFilter().filter(record)

    def test_filter_sets_thread_field_for_non_main_thread(self):
        """record.thread names a non-main thread, at DEBUG level."""
        record = {}

        def make_record():
            record["obj"] = logging.LogRecord(
                name="nubia.test",
                level=logging.DEBUG,
                pathname=__file__,
                lineno=1,
                msg="test message",
                args=None,
                exc_info=None,
            )
            ContextFilter().filter(record["obj"])

        t = threading.Thread(target=make_record, name="worker-1")
        t.start()
        t.join()

        self.assertIn("worker-1", record["obj"].thread)

    def test_filter_leaves_thread_field_empty_on_main_thread(self):
        """record.thread stays empty when filtering happens on the main
        thread (the common case), even at DEBUG level."""
        record = logging.LogRecord(
            name="nubia.test",
            level=logging.DEBUG,
            pathname=__file__,
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )

        ContextFilter().filter(record)

        self.assertEqual(record.thread, "")


if __name__ == "__main__":
    unittest.main()
