#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#

from nubia import command


@command
def example_command1():
    """
    An example command for testing purposes
    """
    return None


@command
async def example_async_command1():
    """
    An example command for testing purposes async
    """
    return None
