#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#

import unittest

from later.unittest import TestCase

from nubia import command
from tests.util import TestShell


class SuperCommandSpecTest(TestCase):
    async def test_super_basics(self):
        this = self

        @command
        class SuperCommand:
            "SuperHelp"

            @command
            async def sub_command(self, arg1: str, arg2: int):
                "SubHelp"
                this.assertEqual(arg1, "giza")
                this.assertEqual(arg2, 22)
                return 45

            @command
            async def another_command(self, arg1: str):
                "AnotherHelp"
                return 22

        shell = TestShell(commands=[SuperCommand])
        self.assertEqual(
            45,
            await shell.run_cli_line(
                "test_shell super-command sub-command --arg1=giza --arg2=22"
            ),
        )
        self.assertEqual(
            22,
            await shell.run_cli_line(
                "test_shell super-command another-command --arg1=giza"
            ),
        )

    async def test_super_common_arguments(self):
        this = self

        @command
        class SuperCommand:
            "SuperHelp"

            def __init__(self, shared: int = 10) -> None:
                self.shared = shared

            @command
            async def sub_command(self, arg1: str, arg2: int):
                "SubHelp"
                this.assertEqual(self.shared, 15)
                this.assertEqual(arg1, "giza")
                this.assertEqual(arg2, 22)
                return 45

        shell = TestShell(commands=[SuperCommand])
        self.assertEqual(
            45,
            await shell.run_cli_line(
                "test_shell super-command --shared=15 "
                "sub-command --arg1=giza --arg2=22"
            ),
        )
        self.assertEqual(
            45,
            await shell.run_cli_line(
                "test_shell super-command sub-command "
                "--arg1=giza --arg2=22 --shared=15"
            ),
        )

    async def test_super_no_docstring(self):
        @command
        class SuperCommand:
            "SuperHelp"

            @command
            async def sub_command(self, arg1: str):
                return f"Hi {arg1}"

        shell = TestShell(commands=[SuperCommand])

        with self.assertRaises(SystemExit):
            await shell.run_cli_line(
                "test_shell super-command sub-command --arg1=human"
            )

    async def test_sync_sub_command(self):
        @command
        class SuperCommand:
            "SuperHelp"

            @command
            def sub_command(self):
                "SubHelp"
                return 45

        shell = TestShell(commands=[SuperCommand])
        self.assertEqual(
            45,
            await shell.run_cli_line("test_shell super-command sub-command"),
        )
