#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.
#

import asyncio
import socket
import typing

from termcolor import cprint

from nubia import argument, command, context
from nubia.internal.typing import validate_mac_address


@command(aliases=["lookup"])
@argument("hosts", description="Hostnames to resolve", aliases=["i"])
@argument("bad_name", name="nice", description="testing")
def lookup_hosts(hosts: typing.List[str], bad_name: int):
    """
    This will lookup the hostnames and print the corresponding IP addresses
    """
    ctx = context.get_context()
    cprint("Input: {}".format(hosts), "yellow")
    cprint("Verbose? {}".format(ctx.verbose), "yellow")
    for host in hosts:
        cprint("{} is {}".format(host, socket.gethostbyname(host)))

    # optional, by default it's 0
    return 0


@command("good-name")
def bad_name():
    """
    This command has a bad function name, but we ask Nubia to register a nicer
    name instead
    """
    cprint("Good Name!", "green")


@command("async-good-name")
async def async_bad_name():
    """
    This command has a bad function name, but we ask Nubia to register a nicer
    name instead
    """
    cprint("This is async!", "green")


@command
@argument("number", type=int)
async def triple(number):
    "Calculates the triple of the input value"
    cprint("Input is {}".format(number))
    cprint("Type of input is {}".format(type(number)))
    cprint("{} * 3 = {}".format(number, number * 3))
    await asyncio.sleep(2)


@command
@argument("number", type=int, positional=True)
def double(number):
    "Calculates the triple of the input value"
    cprint("Input is {}".format(number))
    cprint("Type of input is {}".format(type(number)))
    cprint("{} * 2 = {}".format(number, number * 2))


@command
@argument("number", type=int, positional=True)
@argument("text", type=str)
def pos_and_kv(number: int, text: str = ''):
    "Accepts both positional and keyval args"
    cprint("Input is {}".format(number))
    cprint(f"The text is {text}")


@command
@argument("number", type=int, positional=True)
@argument("text", type=str, positional=True)
def multipos(number: int, text: str):
    "Muliple positional args"
    cprint(f"number is {number}")
    cprint(f"The text is {text}")


@command
@argument("number", type=int, positional=True)
@argument("text", type=str, positional=True)
@argument("mylist", type=list)
@argument("mydict", type=dict)
def multipos_and_kv(number: int, text: str, mylist=None, mydict=None):
    "Muliple positional args"
    cprint(f"number is {number}")
    cprint(f"The text is {text}")
    cprint(f'mylist is {mylist}')
    cprint(f'mydict is {mydict}')


@command("be-blocked")
def be_blocked():
    """
    This command is an example of command that blocked in configerator.
    """

    cprint("If you see me, something is wrong, Bzzz", "red")


@command
@argument("style", description="Pick a style", choices=["test", "toast", "toad"])
@argument("stuff", description="more colors", choices=["red", "green", "blue"])
@argument("code", description="Color code", choices=[12, 13, 14])
def pick(style: str, stuff: typing.List[str], code: int):
    """
    A style picking tool
    """
    cprint("Style is '{}' code is {}".format(style, code), "yellow")


@command
@argument("text", positional=True, nargs=-1)
def ask(text: typing.List[str]):
    """positional argument that accepts infinite list of strings"""
    # More efficient: use shlex.quote() which handles all edge cases
    import shlex
    formatted_text = " ".join(shlex.quote(s) for s in text)
    cprint(f'Got strings: {formatted_text}')

# instead of replacing _ we rely on camelcase to - super-command


@command
class SuperCommand:
    "This is a super command"

    def __init__(self, shared: int = 0) -> None:
        self._shared = shared

    @property
    def shared(self) -> int:
        return self._shared

    """This is the super command help"""

    @command
    @argument("firstname", positional=True)
    def print_name(self, firstname: str):
        """
        print a name
        """
        cprint("My name is: {}".format(firstname))

    @command(aliases=["do"])
    def do_stuff(self, stuff: int):
        """
        doing stuff
        """
        cprint("stuff={}, shared={}".format(stuff, self.shared))


@command
@argument("mac", type=validate_mac_address, description="MAC address (supports both : and . formats, plus regex patterns)")
def test_mac(mac):
    """
    Test command for MAC address parsing without quotes.
    
    Examples:
    - test_mac 00:01:21:ab:cd:8f
    - test_mac 1234.abcd.5678
    - test_mac ~12:34.*
    - test_mac !~abcd.*
    """
    cprint(f"Received MAC address: {mac}", "green")
    cprint(f"Type: {type(mac)}", "yellow")
    return 0


@command
@argument("mac", type=validate_mac_address, positional=True, description="MAC address as positional argument")
def test_mac_pos(mac):
    """
    Test command for MAC address parsing as positional argument.
    
    Examples:
    - test_mac_pos 00:01:21:ab:cd:8f
    - test_mac_pos 1234.abcd.5678
    - test_mac_pos ~12:34.*
    - test_mac_pos !~abcd.*
    """
    cprint(f"Received MAC address: {mac}", "green")
    cprint(f"Type: {type(mac)}", "yellow")
    return 0
