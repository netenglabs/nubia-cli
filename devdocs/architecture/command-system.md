# Command System

This document describes how commands are defined, loaded, registered, and executed in Nubia.

## The `Command` Abstract Base Class

`nubia/internal/cmdbase.py`

`Command` is the base class for all command implementations. Every command object registered with the framework must be a subclass of `Command`.

### Methods

**`get_command_names() -> List[str]`** — Must be overridden. Returns the list of names under which this command is registered (primary name plus any aliases handled at the command level).

**`run_interactive(cmd, args, raw)`** — Must be overridden. Called when the user types the command in the interactive shell. `cmd` is the command name matched, `args` is the unparsed argument string, `raw` is the full original input line.

**`run_cli(args)`** — Called when the command is invoked from the CLI (non-interactive). `args` is an `argparse.Namespace`. Default implementation does nothing.

**`add_arguments(parser)`** — Called during startup to register the command's subparser and arguments with the top-level argparse parser. Default implementation does nothing.

**`get_completions(cmd, document, complete_event) -> Iterable[Completion]`** — Called by the interactive shell to produce autocomplete suggestions. Default returns an empty list.

**`get_help(cmd, *args) -> str`** — Returns the help string for the given command name. A missing or empty help string causes the command to be rejected at registration time.

**`get_cli_aliases() -> List[str]`** — Returns additional names that map to this command in CLI mode only (not shown in `help` output).

**`metadata -> FunctionInspection`** — Property returning the command's `FunctionInspection` metadata. Default returns `{}`. `AutoCommand` overrides this meaningfully.

**`super_command -> bool`** — Property indicating whether this command dispatches to sub-commands. Default `False`.

**`built_in -> bool`** — Property flag used by `HelpCommand` to separate built-in commands from user-defined ones in the help table. Set to `True` in built-in subclasses.

---

## The `AutoCommand` Class

`AutoCommand` is a `Command` subclass that wraps any Python function or class decorated with `@command`. It is the class most user-defined commands become after decoration.

```python
class AutoCommand(Command):
    def __init__(self, fn, options: Optional[Options] = None):
        self._fn = fn
        self._obj_metadata = inspect_object(fn)
        self._is_super_command = len(self.metadata.subcommands) > 0
        ...
```

### Construction

`AutoCommand(fn)` accepts either a plain function or a class. It:

1. Calls `inspect_object(fn)` to produce a `FunctionInspection` describing the function's arguments, types, defaults, and sub-commands.
2. Raises `ValueError` if `fn` has no `@command` decorator or if an unbound method (carrying an unresolved `self`) is passed.
3. If `super_command` is `True` (the wrapped object is a class with `@command`-decorated methods), builds a `WordCompleter` seeded with sub-command names and their help strings.

### FunctionInspection Metadata

`inspect_object` returns a `FunctionInspection` named tuple:

```python
FunctionInspection = namedtuple("FunctionInspection", "arguments command subcommands")
```

- **`command`** — A `Command` named tuple: `(name, help, aliases, exclusive_arguments)`.
- **`arguments`** — `OrderedDict` mapping display-name → `Argument` named tuple. The `Argument` fields are: `arg` (Python parameter name), `description`, `type`, `default_value_set`, `default_value`, `name` (display name), `extra_names` (aliases), `positional`, `choices`, `nargs`.
- **`subcommands`** — List of `(attr_name, FunctionInspection)` pairs for sub-commands. Non-empty only for super-commands.

### `run_interactive` Flow

When the interactive shell dispatches a command to `AutoCommand.run_interactive`:

1. The argument string is parsed by `nubia.internal.parser.parse()` into a `ParseResult` containing key-value pairs and positional values.
2. If this is a super-command, the sub-command token is extracted, validated, and used to instantiate the class (`self._fn(**class_kwargs)`) and select the correct method.
3. Positional arguments are mapped to parameters in declaration order, subject to `positional=True` on each `Argument`.
4. Argument counts are validated (unknown keys, duplicate keys, missing required keys).
5. Each value is type-converted by `apply_typing(value, target_type)`. Failure returns exit code 4.
6. If `choices` is set, values are validated against the allowed set. Failure returns exit code 4.
7. The target function (or method) is called: `await try_await(fn(**args_dict))`.
8. Exceptions during execution are caught, printed to stderr with traceback, and return exit code 1.

### `run_cli` Flow

For CLI mode, `run_cli(args)` receives an `argparse.Namespace`. It calls `get_arguments_for_command(fn, args)` to map parsed namespace attributes back to function parameter names, then calls the function directly.

### Sub-command Dispatch

For super-commands in interactive mode, `AutoCommand` resolves the sub-command name to an attribute name on the class via `_find_subcommand_attr`, then retrieves the bound method from the class instance. In CLI mode, `args._subcmd` holds the sub-command name (set by argparse via `dest="_subcmd"`).

---

## Command Loading

`nubia/internal/cmdloader.py`

`load_commands(base_package)` is a generator that yields all `@command`-decorated objects found in a package tree.

```python
def load_commands(base_package):
    yield from _walk_package(base_package.__name__, path)
```

### How it works

1. `_walk_package` uses `pkgutil.walk_packages` to recursively enumerate all modules under `base_package`.
2. For each non-package module, `_walk_module` iterates `dir(module)`, skipping private names (starting with `_`).
3. Any attribute that has a `__command` attribute (set by the `@command` decorator) is yielded.

The caller (typically `nubia.Nubia`) wraps each yielded object in an `AutoCommand` and registers it with the `CommandsRegistry`.

---

## The Registry

`nubia/internal/registry.py`

`CommandsRegistry` maps command name strings to `Command` instances and coordinates event dispatch to listeners.

### Internal State

- `_cmd_instance_map: Dict[str, Command]` — maps lowercased command names to `Command` objects. Both primary names and aliases are stored in this map.
- `_completer: WordCompleter` — used by the interactive shell to offer top-level command completions.
- `_listeners: List[Listener]` — objects that receive event messages (connected, disconnected, etc.).

### `register_command(cmd_instance, override=False)`

1. Calls `cmd_instance.get_command_names()` to obtain all names.
2. Rejects commands with no help string (warns and returns `None`).
3. Calls `await cmd_instance.add_arguments(self._parser)` so the command registers its argparse subparser.
4. Checks for name conflicts unless `override=True`.
5. Stores `cmd_instance` under each name (lowercased) in `_cmd_instance_map`.
6. Registers CLI aliases from `get_cli_aliases()` in `_cmd_instance_map` but not in the completer.
7. If `cmd_instance` implements `Listener`, appends it to `_listeners`.

### Lookup

`find_command(cmd)` returns `_cmd_instance_map.get(cmd.lower())`. The `__contains__` operator checks the same map. Lookup is case-insensitive.

### Event Dispatch

`dispatch_message(msg, *args, **kwargs)` iterates `_listeners` in order and calls `await try_await(listener.react(msg, ...))`. Listeners registered with `register_priority_listener` are inserted at index 0.

---

## Built-in Commands

`nubia/internal/commands/builtin.py`, `nubia/internal/commands/help.py`

All built-in commands set `self._built_in = True`, which causes `HelpCommand` to display them in a separate "Built-in Commands" table.

### `Connect`

Registered as `"connect"`. When run (interactive or CLI), dispatches `Message.CONNECTED` to all registry listeners. This is the mechanism for triggering any "on connect" initialization logic in plugins.

### `Exit`

Registered as `["quit", "q", "exit"]`. Raises `EOFError` from `run_interactive`, which the interactive loop catches to terminate the REPL.

### `Verbose`

Registered as `":verbose"`. The leading colon prevents collision with user-defined commands. Without arguments, prints the current verbosity level. With an argument, calls `ctx.set_verbose(args)`.

### `HelpCommand`

Registered as `["help", "?"]`. Without arguments, queries the registry for all commands and renders two `PrettyTable` instances: one for user commands, one for built-ins. With a command name argument, prints the long-form help for that specific command. Completions delegate to the registry's top-level `WordCompleter`.

---

## Full Lifecycle

The following sequence describes a command from decoration to execution.

1. **Decoration** — Developer applies `@command` to a function or class. The decorator sets `fn.__command` dict with `name`, `help`, `aliases`, `exclusive_arguments`. Optionally, `@argument` decorators set `fn.__arguments_decorator_specs`.

2. **Discovery** — At startup, `load_commands(plugin_package)` walks the package tree and yields all objects with `__command`.

3. **Wrapping** — Each yielded object is passed to `AutoCommand(fn)`, which calls `inspect_object(fn)` to build the `FunctionInspection`.

4. **Registration** — `CommandsRegistry.register_command(auto_cmd)` is awaited. The command adds its argparse subparser via `add_arguments`, and its names are entered into `_cmd_instance_map` and `_completer`.

5. **Input** (interactive mode) — The user types a command. The REPL matches the first token against the registry via `find_command`. If found, `await cmd.run_interactive(cmd_name, rest_of_input, full_line)` is called.

6. **Parsing** — Inside `run_interactive`, `parser.parse(args)` tokenizes the argument string into key-value pairs and positionals.

7. **Type conversion** — For each argument, `apply_typing(value, target_type)` converts the string representation to the declared Python type. Returns exit code 4 on failure.

8. **Execution** — The resolved function is called: `await try_await(fn(**args_dict))`. Runtime exceptions return exit code 1.

9. **Input** (CLI mode) — `argparse` parses `sys.argv`. The matched `Command.run_cli(parsed_namespace)` is called. `get_arguments_for_command` maps namespace attributes back to function parameter names before calling the function.

---

## Super-Commands (Class-Based Commands)

A class decorated with `@command` becomes a super-command. Its public methods decorated with `@command` become sub-commands.

```python
@command("network", help="Network management commands")
class Network:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose

    @command("show", help="Show network interfaces")
    def show(self, interface: str):
        ...
```

Rules:
- The class constructor may only have parameters with default values. Required constructor parameters are rejected by `inspect_object`.
- `positional=True` is not allowed on class-level arguments.
- In interactive mode, the class is instantiated with the class-level arguments extracted first, then the sub-command method is called with remaining arguments.
- In CLI mode, argparse creates a nested sub-parser with `dest="_subcmd"`.
- Sub-commands without a help string are silently skipped with a warning.

`AutoCommand.super_command` returns `True` when `len(self.metadata.subcommands) > 0`.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (or `None` return from the command function) |
| 1 | Runtime exception during command execution |
| 2 | Argument validation error (unknown key, duplicate key, wrong positional count, bad sub-command) |
| 3 | Missing required argument |
| 4 | Type conversion failure or `choices` validation failure |
