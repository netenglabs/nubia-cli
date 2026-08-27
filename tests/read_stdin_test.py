#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#
import tempfile
from unittest import mock

from later.unittest import TestCase

from nubia import argument, command
from tests.util import TestShell


class ReadStdinTest(TestCase):
    async def test_read_from_stdin(self):
        @command
        @argument("arg")
        def test_command(arg: str) -> int:
            """
            Sample Docstring
            """
            self.assertEqual("test_arg", arg)
            return 22

        command_file = tempfile.NamedTemporaryFile(
            mode="w+", prefix="test_read_from_stdin", delete=True
        )
        command_file.write("test-command arg=test_arg")
        command_file.flush()
        command_file.seek(0)
        shell = TestShell(commands=[test_command])
        with mock.patch("sys.stdin", command_file):
            self.assertEqual(22, await shell.run_async(cli_args=["", "connect"]))
