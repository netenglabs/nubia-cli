# Testing

This guide explains the test infrastructure, the patterns used in the existing test
suite, and how to add new tests.

---

## Test Infrastructure

**Framework:** `pytest`, plus `later.unittest.TestCase` for tests that exercise async
command functions.

**Run the tests:**

```bash
poetry run pytest
```

Or run a single file:

```bash
poetry run pytest tests/commands_test.py
```

**Test file locations:** all tests live under `tests/`.

**Dependencies** (declared in `pyproject.toml` under `[tool.poetry.dev-dependencies]`):
- `pytest ^8.3` (the newest 8.x release still supporting Python 3.8; pytest
  8.4+ raised its floor to Python 3.9)
- `pytest-cov ^4.1` — used in CI for `--cov=nubia` coverage reporting
- `later ~23.11` — provides `later.unittest.TestCase`, which handles the asyncio event
  loop for async test methods

---

## Test Patterns Used in the Codebase

### Setting Up a Nubia Instance

Tests never instantiate `Nubia` directly with a real plugin. Instead they use
`TestShell` from `tests/util.py`, which wraps `Nubia` in testing mode and accepts a
plain list of command objects:

```python
# tests/util.py (abridged)
from nubia import Nubia, PluginInterface
from nubia.internal.cmdbase import AutoCommand, Command
from nubia.internal.blackcmd import CommandBlacklist


class TestPlugin(PluginInterface):
    def __init__(self, commands):
        self._commands = commands

    def get_commands(self):
        return [c if isinstance(c, Command) else AutoCommand(c) for c in self._commands]

    def getBlacklistPlugin(self):
        blacklist = CommandBlacklist()
        blacklist.add_blocked_command("blocked")
        return blacklist


class TestShell(Nubia):
    def __init__(self, commands, name="test_shell"):
        super().__init__(name, plugin=TestPlugin(commands), testing=True)

    async def run_cli_line(self, raw_line):
        cli_args_list = raw_line.split()
        args = await self._pre_run(cli_args_list)
        return await self.run_cli(args)

    async def run_interactive_line(self, raw_line, cli_args=None):
        cli_args = cli_args or "test_shell connect"
        args = await self._pre_run(cli_args.split())
        io_loop = await self._create_interactive_io_loop(args)
        return await io_loop.parse_and_evaluate(raw_line)
```

### Invoking Commands Programmatically

Two methods are provided:

- `await shell.run_cli_line("test_shell command-name --flag value")` — exercises the
  argparse code path. The first token must be the shell name; it is consumed as `argv[0]`.
- `await shell.run_interactive_line("command-name flag=value")` — exercises the
  pyparsing code path used in interactive (REPL) mode.

Both return the value returned by the command function. A `SystemExit` raised by
argparse (e.g., for unknown flags or exclusive group violations) propagates to the test.

Typical async test structure:

```python
from later.unittest import TestCase
from nubia import command, argument
from tests.util import TestShell


class MyCommandTest(TestCase):
    async def test_something(self):
        @command
        async def my_cmd(value: int = 0) -> int:
            """My command help"""
            return value * 2

        shell = TestShell(commands=[my_cmd])
        self.assertEqual(10, await shell.run_cli_line("test_shell my-cmd --value 5"))
        self.assertEqual(10, await shell.run_interactive_line("my-cmd value=5"))
```

For synchronous commands use the same pattern; `TestCase` awaits the coroutine but the
command itself does not need to be async.

### The sample_package/ Fixture

`tests/sample_package/` is a realistic Python package used by `cmdloader_test.py` to
verify package walking behavior. Its layout:

```
tests/sample_package/
    __init__.py          # empty
    commands.py          # example_command1, example_async_command1
    subpackage/
        __init__.py      # empty
        more_commands.py # example_command2, SuperCommand (with sub_command,
                         #                                  sub_command_async)
```

`cmdloader.load_commands(sample_package)` yields 4 objects:
`example_command1`, `example_async_command1`, `example_command2`, and `SuperCommand`.

This fixture exists to test that:
- Nested sub-packages are discovered.
- Both async and sync commands are found.
- Both function commands and super-command classes are yielded.

### The empty_package/ Fixture

`tests/empty_package/` contains only an empty `__init__.py`. It verifies that
`load_commands` returns an empty list when no `@command`-decorated objects exist.

---

## What Each Test File Covers

**`typing_test.py`**
Tests the type system in two independent layers:
- `SimpleValuesBuilderTest` — `build_value(raw_string, type)`: how strings are coerced
  into `int`, `str`, `List`, `Mapping`, `Tuple`, and nested combinations. Uses direct
  calls to `nubia.internal.typing.builder.build_value`.
- `ArgparseExtensionTest` — argparse integration: how `@argument` decorators register
  flags, handle aliases, enforce naming conventions, validate dict/list types, and how
  exclusive argument groups work. Uses a local `ContainedParser` subclass that raises
  `ParseError` instead of calling `sys.exit`.

**`commands_test.py`**
End-to-end command execution tests using `TestShell`. Covers:
- Sync and async commands
- Name derivation (underscore-to-hyphen, explicit name, aliases)
- Approximate command matching in interactive mode
- Default and optional arguments
- Positional arguments (single, multiple, mixed with named)
- Exclusive argument groups
- Negative numeric arguments
- The `@deprecated` decorator
- List type lifting (single value vs multi-value)
- Blacklisted commands

**`supercommands_test.py`**
Tests `@command`-decorated classes:
- Basic subcommand invocation via CLI
- Shared (`__init__`) arguments placed before or after the subcommand name
- Subcommands without docstrings are excluded (raises `SystemExit` on invocation)
- Sync subcommands work as well as async ones

**`inspection_test.py`**
Tests `nubia.internal.typing.inspect_object`, which extracts metadata from decorated
functions and classes. Verifies the `InspectionData` structure: command name, help
text, argument map, and subcommand list.

**`helpers_test.py`**
Unit tests for utility functions in `nubia.internal.helpers`:
- `function_to_str` — string representation of a function with optional module path
  and argument list
- `catchall` — swallows generic exceptions but lets `KeyboardInterrupt` and
  `SystemExit` propagate
- `find_approx` — prefix and Levenshtein-based approximate name matching
- `is_optional_type` — distinguishes `Optional[X]` from other `Union` types

**`cmdloader_test.py`**
Tests `nubia.internal.cmdloader.load_commands`:
- `None` input returns an empty list
- An empty package returns an empty list
- `sample_package` returns the expected 4 command objects from both levels of nesting

**`read_stdin_test.py`**
Tests that the shell can read commands from a file redirected to `stdin`, which is the
mechanism used for non-interactive scripted runs. Writes a command to a temp file,
redirects `stdin` to it, and asserts the command executes correctly via `shell.run_async`.

---

## How to Add a Test

### Where to Put It

- Add to an existing `tests/*_test.py` file if the test logically belongs there.
- Create a new `tests/myfeature_test.py` for a new subsystem.
- For command fixtures shared across multiple tests, add them to
  `tests/sample_package/` or a new subpackage.

### How to Create a Command Fixture

Define the command inline inside the test method. This keeps fixtures local and avoids
polluting the global command namespace:

```python
from later.unittest import TestCase
from nubia import argument, command
from tests.util import TestShell


class MyFeatureTest(TestCase):
    async def test_my_feature(self):
        @command
        @argument("count", description="How many times")
        async def repeat(count: int = 1) -> int:
            """Repeat count times"""
            return count

        shell = TestShell(commands=[repeat])
        self.assertEqual(3, await shell.run_cli_line("test_shell repeat --count 3"))
        self.assertEqual(3, await shell.run_interactive_line("repeat count=3"))
```

For synchronous commands, `TestCase` still works — just omit `async`/`await` on the
command function.

### How to Assert on Output or Return Values

- **Return value:** `run_cli_line` and `run_interactive_line` both return the value
  returned by the command function. Use `assertEqual`, `assertIsNone`, etc.
- **Raised exceptions:** use `assertRaises(SystemExit)` to check that argparse rejects
  invalid input (e.g., missing required args, exclusive group violations).
- **Printed output:** capture stdout with `unittest.mock.patch("sys.stdout", ...)` or
  `io.StringIO` if you need to assert on printed text. Most existing tests rely on
  return values instead.
- **Blacklist behavior:** the `TestPlugin` blacklists the command name `"blocked"`. A
  blacklisted command returns `1` instead of executing.
