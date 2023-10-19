#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#


from pyparsing import ParseResults


class CommandParseError(Exception):

    def __init__(self, msg, remaining: str, partial_result: ParseResults,
                 col: int, *args, **kwargs):
        self.remaining = remaining
        self.partial_result = partial_result
        self.col = col
        super().__init__(msg, *args, **kwargs)



class CommandError(Exception):
    pass


class UnknownCommand(CommandError):
    pass


class ArgsValidationError(Exception):
    pass
