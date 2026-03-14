# Adding a Command to Nubia

This guide covers everything needed to add a new command, from a simple function to a
super-command with subcommands, and explains how commands are discovered and registered.

---

## Simple Function Commands

### Minimal Example

Decorate any function with `@command`. The function's docstring becomes the help text.
Underscores in the function name are converted to hyphens for the CLI name
(e.g., `lookup_hosts` becomes `lookup-hosts`).

```python
from nubia import command

@command
def say_hello():
    "Prints a greeting"
    print("Hello!")
```

To override the generated name, pass a string to `@command`:

```python
@command("good-name")
def bad_function_name():
    "Exposed as good-name, not bad-function-name"
    pass
```

### Using @argument

Use `@argument` to add metadata to individual parameters. The decorator must name the
parameter it annotates using the Python parameter name (underscores, not hyphens).

```python
import typing
from nubia import argument, command

@command(aliases=["lookup"])
@argument("hosts", description="Hostnames to resolve", aliases=["i"])
def lookup_hosts(hosts: typing.List[str], count: int = 1):
    """
    Resolve hostnames to IP addresses
    """
    ...
```

Supported `@argument` keyword arguments:

| Keyword | Purpose |
|---|---|
| `description` | Help text for the argument |
| `aliases` | Alternative names (single-char becomes `-x`, longer becomes `--name`) |
| `name` | Override the CLI flag name while keeping the Python parameter name |
| `choices` | Restrict input to an enumerated set of values |
| `nargs` | Number of values (`-1` means unlimited, passed as a list) |
| `type` | Explicit type converter callable |
| `positional` | If `True`, the argument is consumed positionally rather than by flag |

### Choices

```python
@command
@argument("style", description="Pick a style", choices=["test", "toast", "toad"])
@argument("code", description="Color code", choices=[12, 13, 14])
def pick(style: str, code: int):
    "A style picking tool"
    ...
```

### Optional Arguments

Use `Optional[T]` with a default of `None` to make an argument optional in both modes:

```python
import typing
from nubia import argument, command

@command
@argument("hosts", description="Hostnames")
def lookup(hosts: typing.Optional[typing.List[str]] = None):
    "Look up hosts if provided"
    hosts = hosts or []
    ...
```

### List and Dict Arguments

Type annotations drive parsing in both interactive and CLI modes.

**List** — CLI: space-separated values after the flag. Interactive: `arg=[a, b]` or comma-separated `arg=a,b`.

```python
@command
@argument("servers", description="Server list")
def ping_all(servers: typing.List[str]):
    "Ping all servers"
    ...
```

**Dict** — CLI: `key=value` pairs separated by semicolons. Interactive: same format or JSON.

```python
@command
@argument("tags", description="Key/value tags")
def tag_resource(tags: typing.Mapping[str, str]):
    "Apply tags"
    ...
```

CLI usage: `tag-resource --tags env=prod;owner=alice`
Interactive usage: `tag-resource tags=env:prod;owner:alice`

### Positional Arguments

```python
@command
@argument("number", type=int, positional=True)
def double(number):
    "Double a number"
    print(number * 2)
```

Multiple positionals are bound in Python parameter order regardless of decorator order.
Positional arguments cannot have defaults and cannot have aliases.

An unlimited positional list uses `nargs=-1`:

```python
@command
@argument("text", positional=True, nargs=-1)
def ask(text: typing.List[str]):
    "Accept any number of words"
    print(" ".join(text))
```

### Async Commands

Declare the function `async`. Nubia runs it inside its event loop. Both interactive
and CLI modes support async commands identically.

```python
import asyncio
from nubia import command

@command
async def slow_operation():
    "An async command"
    await asyncio.sleep(1)
    print("Done")
```

---

## Super-Commands (Classes with Subcommands)

A super-command groups related subcommands under a shared namespace. Decorate a class
with `@command` and decorate each method that should be a subcommand with `@command`.

### Basic Structure

```python
from nubia import argument, command

@command
class SuperCommand:
    "This is a super command"

    @command
    @argument("firstname", positional=True)
    def print_name(self, firstname: str):
        """
        Print a name
        """
        print(f"My name is: {firstname}")

    @command(aliases=["do"])
    def do_stuff(self, stuff: int):
        """
        Do stuff
        """
        print(f"stuff={stuff}")
```

- The class name `SuperCommand` becomes `super-command` (CamelCase converted to kebab-case).
- Method names follow the same transformation: `print_name` becomes `print-name`.
- Every subcommand method **must have a docstring**; methods without one are silently
  excluded from the command registry.

CLI invocation: `myapp super-command print-name Alice`
Interactive invocation: `super-command print-name Alice`

### Shared (Common) Arguments

Arguments accepted by `__init__` are exposed as flags that apply to all subcommands.
They can be placed before or after the subcommand name on the CLI.

```python
@command
class SuperCommand:
    "This is a super command"

    def __init__(self, shared: int = 0) -> None:
        self._shared = shared

    @command
    def do_stuff(self, stuff: int):
        """
        Do stuff using the shared value
        """
        print(f"stuff={stuff}, shared={self._shared}")
```

CLI usage: `super-command --shared=15 do-stuff --stuff=7`
or: `super-command do-stuff --stuff=7 --shared=15`

### Exclusive Arguments

Pass `exclusive_arguments` to `@command` to create a mutually exclusive group.
The value is a list of parameter names, or a list of lists for multiple groups.

```python
@command(exclusive_arguments=["arg1", "arg2"])
@argument("arg1")
@argument("arg2")
async def my_command(arg1: str = "", arg2: str = ""):
    """
    Only arg1 or arg2 may be supplied, not both
    """
    ...
```

Mutual exclusion is enforced in CLI mode by argparse. Interactive mode does not enforce it.

---

## Registering Commands

### Adding to an Existing Package

The simplest case: add a new decorated function or class to an existing module inside
an already-registered command package.

In the example application the command package is `commands` (the `example/commands/`
directory). Adding a function to `example/commands/sample_commands.py` makes it
available immediately — no registration call is required.

### Adding a New Module Inside the Package

Create a new `.py` file anywhere inside the package directory (including subdirectories).
`cmdloader` recurses the entire package tree, so the file will be found automatically.

For example, `example/commands/more/moar_commands.py` is discovered because it lives
under `example/commands/`:

```python
# example/commands/more/moar_commands.py
from nubia import command

@command
def another_command():
    "Just a simple do nothing command"
    return None
```

No changes to `__init__.py` files are needed as long as they exist (even if empty).

### Adding a New Top-Level Package

Pass the new package to `Nubia` via `command_pkgs`:

```python
import commands
import my_new_commands
from nubia import Nubia, Options

shell = Nubia(
    name="myapp",
    command_pkgs=[commands, my_new_commands],
    plugin=plugin,
)
```

`command_pkgs` accepts a single package or a list of packages.

### How cmdloader Discovers Commands

`nubia.internal.cmdloader.load_commands` uses `pkgutil.walk_packages` to recurse the
package tree. For every non-package module it finds, it inspects every public attribute
(no leading underscore) and yields those that have the `__command` attribute set by the
`@command` decorator.

This means:

- The `@command` decorator must be applied at module level (or the decorated object must
  be importable from a module-level name).
- Private names (prefixed with `_`) are skipped.
- The package directory must contain `__init__.py` at every level.

---

## Interactive vs CLI Mode Differences

The same decorated function works in both modes, but the two modes use different parsers.

| Aspect | CLI mode | Interactive mode |
|---|---|---|
| Parser | `argparse` | `pyparsing` |
| List syntax | `--arg a b` (space-separated) | `arg=[a, b]` or `arg=a,b` |
| Dict syntax | `--tags env=prod;owner=alice` | `tags=env:prod;owner:alice` |
| Approximate matching | Not supported (exact name required) | Supported (prefix + Levenshtein) |
| Exclusive groups | Enforced by argparse | Not enforced |
| Entry point | `shell.run()` dispatches to argparse | `io_loop.parse_and_evaluate(line)` |

The function body is identical in both cases. Nubia converts the parsed tokens into the
correct Python types before calling the function.

See `tests/commands_test.py` for side-by-side examples of CLI and interactive
invocations of the same command.
