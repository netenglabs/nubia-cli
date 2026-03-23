# Architecture Overview

## What Nubia Is

Nubia is a Python framework that turns annotated functions and classes into both an interactive shell and a traditional CLI. A developer decorates a function with `@command` (and optionally `@argument` for richer metadata), passes the containing package to `Nubia`, and gets:

- A prompt-toolkit REPL where the command is available with tab-completion, syntax highlighting, and inline help.
- An argparse-backed CLI where the command is a subcommand (e.g. `mytool lookup --hosts a,b,c`).
- Automatic type coercion in both modes, driven by Python type annotations.

The framework handles the mechanics of parsing, dispatch, type conversion, and completion. Application code only needs to implement the business logic inside the decorated function.

---

## Execution Modes

Nubia supports three execution modes, selected automatically based on how the binary is invoked.

### Interactive Mode

Activated when no subcommand is passed on the command line (`args._cmd == "connect"`) and `sys.stdin` is a TTY.

`IOLoop` runs a prompt-toolkit `PromptSession` in a loop. Each line entered by the user is passed to `IOLoop.parse_and_evaluate`, which splits it into a command name and a remainder string, looks up the `Command` in `CommandsRegistry`, then calls `Command.run_interactive(cmd, args_str, raw)`.

`AutoCommand.run_interactive` uses the pyparsing-based `parser.parse` (in `nubia/internal/parser.py`) to tokenize the remainder into positional values and `key=value` pairs. It then validates and coerces arguments before calling the underlying Python function.

History, editing mode (Emacs/Vi), syntax highlighting (`NubiaLexer`), and the status bar are all configured in `IOLoop._build_cli`.

### CLI Mode

Activated when a recognized subcommand name is passed on the command line.

`Nubia._pre_run` builds an `argparse.ArgumentParser` and registers each command's arguments via `Command.add_arguments`. `AutoCommand.add_arguments` delegates to `register_command` in `nubia/internal/typing/argparse.py`, which inspects the `FunctionInspection` metadata and calls `parser.add_argument` for each parameter.

After argparse parses `sys.argv`, `Nubia.run_cli` calls `Command.run_cli(args)`. `AutoCommand.run_cli` extracts the relevant kwargs from the `argparse.Namespace` and calls the Python function directly.

### Stdin Mode

A degenerate case of interactive mode: activated when no subcommand is passed but `sys.stdin` is not a TTY (i.e. input is piped). `Nubia.start_interactive` reads lines from stdin and passes each to `IOLoop.parse_and_evaluate`. The effect is that the interactive parser is used but without the REPL prompt.

---

## Component Map

```
Nubia (nubia/internal/nubia.py)
  |
  |-- PluginInterface (nubia/internal/plugin_interface.py)
  |     Provides: context factory, opts_parser, command list, listeners,
  |               status bar, prompt tokens, logging setup, usage logger,
  |               args validation, blacklist, session logger
  |
  |-- Context (nubia/internal/context.py)
  |     Global singleton. Holds binary name, parsed args, registry reference,
  |     current command name. Subclass to store application state.
  |
  |-- CommandsRegistry (nubia/internal/registry.py)
  |     Maps command name strings -> Command instances.
  |     Holds a WordCompleter for top-level command name completion.
  |     Dispatches Message events to registered Listeners.
  |
  |-- Command / AutoCommand (nubia/internal/cmdbase.py)
  |     Command: abstract base. Subclass for full manual control.
  |     AutoCommand: wraps a @command-decorated function or class.
  |       - run_interactive: uses parser.py + apply_typing
  |       - run_cli: uses argparse Namespace + apply_typing
  |       - get_completions: delegates to AutoCommandCompletion state machine
  |
  |-- Type System (nubia/internal/typing/)
  |     __init__.py   -- @command, @argument decorators; inspect_object;
  |                      FunctionInspection / Argument / Command namedtuples
  |     inspect.py    -- type predicate helpers (is_list_type, is_mapping_type, etc.)
  |     builder.py    -- apply_typing: converts parsed strings to target Python types
  |     argparse.py   -- register_command: registers Argument metadata with argparse
  |
  |-- IOLoop (nubia/internal/interactive.py)          [interactive mode only]
  |     Owns the PromptSession. Resolves commands. Calls run_interactive.
  |     ShellCompleter: delegates to registry then to each Command.
  |
  |-- parser (nubia/internal/parser.py)               [interactive mode only]
  |     pyparsing grammar: parses "subcmd positionals key=value ..." strings.
  |
  |-- AutoCommandCompletion (nubia/internal/completion.py)  [interactive mode only]
  |     State machine that produces Completion objects for partially-typed
  |     argument names and values.
  |
  |-- Options (nubia/internal/options.py)
  |     Dataclass: persistent_history, auto_execute_single_suggestions,
  |     limit_visible_choices. Passed through from Nubia to IOLoop and AutoCommand.
  |
  |-- eventbus (nubia/internal/io/eventbus.py)
        Message constants (CONNECTED=1). Listener base class with react().
```

---

## Key Design Patterns

### Decorator Pattern — `@command`, `@argument`

`nubia/internal/typing/__init__.py`

`@command` writes a `__command` dict onto the function or class object. `@argument` writes into `__arguments_decorator_specs`. Neither decorator changes the function's behavior; they only attach metadata. `inspect_object` reads this metadata and returns a `FunctionInspection` namedtuple, which all downstream components consume.

Python 3 type annotations on function parameters are read via `inspect.getfullargspec` and merged with `@argument(type=...)` at `inspect_object` time. Either form is valid; conflicts raise `TypeError`.

### Registry Pattern — `CommandsRegistry`

`nubia/internal/registry.py`

All `Command` instances are stored in `CommandsRegistry._cmd_instance_map`, keyed by lowercase command name (and aliases). The registry is the single source of truth for command lookup in both interactive dispatch (`find_command`) and CLI routing (`run_cli`). It also owns the top-level `WordCompleter` used by `ShellCompleter`.

Commands are registered during `Nubia._pre_run` in priority order: built-ins first, then plugin commands, then commands loaded from `command_pkgs`. Later registrations with `override=True` replace earlier ones, allowing the application to override built-ins.

### Observer Pattern — `Listener` / `Message`

`nubia/internal/io/eventbus.py`

`Listener` is a base class with a `react(msg, *args, **kwargs)` coroutine. `CommandsRegistry.dispatch_message` broadcasts a message to all registered listeners in order. Currently only `Message.CONNECTED` is defined, which maps to `on_connected` callbacks.

`Context` and `IOLoop` both implement `Listener`. The plugin can return additional listener classes from `PluginInterface.get_listeners()`; these are instantiated by `CommandsRegistry.__init__` and registered automatically.

### Singleton Pattern — Global Context

`nubia/internal/context.py`

`context._ctx` is a module-level variable set once by `Nubia.__init__` to the instance returned by `PluginInterface.create_context()`. `context.get_context()` is a simple getter. Commands and other components call `get_context()` to access application state without holding an explicit reference to the `Nubia` object. The `Context` class is protected against concurrent access with an `RLock`.

To expose application-specific state (e.g. a connection object), subclass `Context` and override `PluginInterface.create_context()` to return an instance of the subclass.

### Strategy Pattern — Parsing

Interactive mode and CLI mode use entirely different parsing strategies for the same command metadata. In CLI mode, `register_command` (in `argparse.py`) translates `FunctionInspection` into argparse `add_argument` calls; argparse then handles tokenization. In interactive mode, `parser.parse` (pyparsing grammar in `parser.py`) handles tokenization, and `apply_typing` in `builder.py` performs coercion. `AutoCommand` contains both `run_interactive` and `run_cli` methods and selects the appropriate path.

### Adapter Pattern — `AutoCommand`

`nubia/internal/cmdbase.py`

`AutoCommand` is an adapter: it wraps an arbitrary `@command`-decorated callable and presents the `Command` interface (`run_interactive`, `run_cli`, `add_arguments`, `get_command_names`, `get_completions`, `get_help`) expected by the rest of the framework. This is what allows application code to be plain Python functions or classes with no inheritance from framework types.

For super commands (classes), `AutoCommand` further adapts: it instantiates the class with the class-level constructor arguments, then dispatches to the appropriate method based on the parsed sub-command token.

---

## File Reference

| File | Primary Responsibility |
|---|---|
| `nubia/internal/nubia.py` | `Nubia` class — top-level orchestrator, mode selection, startup |
| `nubia/internal/cmdbase.py` | `Command` (abstract base), `AutoCommand` (decorator adapter) |
| `nubia/internal/context.py` | `Context` singleton and `get_context()` accessor |
| `nubia/internal/registry.py` | `CommandsRegistry` — command lookup, listener dispatch |
| `nubia/internal/interactive.py` | `IOLoop` (REPL loop), `ShellCompleter` |
| `nubia/internal/parser.py` | pyparsing grammar for interactive input |
| `nubia/internal/completion.py` | `AutoCommandCompletion` state machine |
| `nubia/internal/plugin_interface.py` | `PluginInterface` — all customization hooks |
| `nubia/internal/options.py` | `Options` dataclass |
| `nubia/internal/cmdloader.py` | Package walker that discovers `@command` objects |
| `nubia/internal/io/eventbus.py` | `Listener`, `Message` |
| `nubia/internal/typing/__init__.py` | `@command`, `@argument`, `inspect_object`, named tuples |
| `nubia/internal/typing/builder.py` | `apply_typing` — string-to-Python type coercion |
| `nubia/internal/typing/inspect.py` | Type predicate helpers |
| `nubia/internal/typing/argparse.py` | `register_command` — argparse integration |
