# Nubia Developer Documentation

Nubia is a lightweight Python framework for building CLI applications and interactive shells. Originally developed at Facebook for the LogDevice interactive shell (`ldshell`), it has been extracted as a reusable library. The core idea: decorating a Python function with `@command` (and optionally `@argument`) exposes it in both an interactive REPL and as a traditional argparse-driven CLI subcommand, with no additional wiring required.

---

## Documentation Index

### Architecture

High-level descriptions of what components exist and how they fit together.

| Document | Description |
|---|---|
| [architecture/overview.md](architecture/overview.md) | Component map, execution modes, and design patterns used throughout the codebase |
| [architecture/command-system.md](architecture/command-system.md) | Command and AutoCommand classes, registry, command loading, lifecycle, exit codes |
| [architecture/type-system.md](architecture/type-system.md) | `@command`/`@argument` decorators, type inspection, conversion, and argparse integration |
| [architecture/interactive-shell.md](architecture/interactive-shell.md) | IOLoop, prompt-toolkit, syntax highlighting, auto-completion state machine |
| [architecture/plugin-interface.md](architecture/plugin-interface.md) | All PluginInterface hooks, custom Context, StatusBar, and Options |

### Internals

Detailed mechanics of individual subsystems.

| Document | Description |
|---|---|
| [internals/data-flows.md](internals/data-flows.md) | Step-by-step flows for command loading, interactive mode, CLI mode, and stdin mode |
| [internals/context-and-registry.md](internals/context-and-registry.md) | Context singleton, CommandsRegistry internals, and the event bus |
| [internals/parsing.md](internals/parsing.md) | pyparsing grammar, argparse integration, and the completion state machine |

### Guides

Task-oriented documentation for common modifications.

| Document | Description |
|---|---|
| [guides/adding-a-command.md](guides/adding-a-command.md) | Simple commands, super-commands, argument types, async, and package registration |
| [guides/extending-nubia.md](guides/extending-nubia.md) | Custom plugin, context, status bar, event listeners, and argument validation |
| [guides/testing.md](guides/testing.md) | Test infrastructure, patterns, fixtures, and how to add new tests |

---

## Organization

```
devdocs/
  README.md            # this file — index and navigation guide
  architecture/        # what exists and how components relate
  internals/           # how individual subsystems work in detail
  guides/              # how to accomplish specific tasks
```

The three layers are intentionally separate. Architecture documents answer "what is this?", internals answer "how does this work?", and guides answer "how do I do X?". Guides link to architecture/internals for background rather than duplicating explanations.

---

## Where to Start

**Understand the overall system before touching anything.**
Start with [architecture/overview.md](architecture/overview.md), then [internals/data-flows.md](internals/data-flows.md).

**Add a new command.**
Read [guides/adding-a-command.md](guides/adding-a-command.md), then [architecture/command-system.md](architecture/command-system.md) for how commands reach the registry and both execution modes.

**Customize the prompt, status bar, or plugin behavior.**
Read [guides/extending-nubia.md](guides/extending-nubia.md) and [architecture/plugin-interface.md](architecture/plugin-interface.md).

**Understand type coercion or fix a type-related bug.**
Read [architecture/type-system.md](architecture/type-system.md), which covers the path from `@argument(type=...)` through `apply_typing` in `builder.py`.

**Modify or debug tab completion.**
Read [architecture/interactive-shell.md](architecture/interactive-shell.md) (completion section) and [internals/parsing.md](internals/parsing.md) (completion state machine).

**Write tests for a command.**
Read [guides/testing.md](guides/testing.md) and look at `tests/util.py` and the existing test suite for patterns.
