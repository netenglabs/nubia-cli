# Context and Registry

These two objects form the shared state backbone that all parts of Nubia read
from and write to. The event bus ties them together.

---

## Context singleton

**File:** `nubia/internal/context.py`

### Purpose

`Context` is a process-wide singleton that carries state that must be
accessible to plugins, commands, and the runtime without explicit argument
threading. It also acts as a `Listener` (see Event Bus below).

### State fields

| Field | Type | Description |
|---|---|---|
| `_binary_name` | `str` | The name passed to `Nubia.__init__()`. Used in the prompt and history file path. |
| `_registry` | `CommandsRegistry` | Back-reference set during `_pre_run`. |
| `_args` | `argparse.Namespace` (deep-copied) | The parsed CLI arguments for the current invocation. |
| `_cmd` | `str` | Name of the command currently executing. Set just before `fn(**args_dict)` is called in `run_interactive`. |
| `_raw_cmd` | `str` | The full input string as typed by the user, before parsing. |
| `_testing` | `bool` | Test mode flag. |
| `_lock` | `threading.RLock` | Guards all mutable state below. |

### Thread safety

All property setters and getters that touch mutable state use `with self._lock`.
`_binary_name` is set once at startup and never mutated; it has no lock.
`RLock` (re-entrant lock) is used so that a thread holding the lock can call
other Context methods without deadlocking.

### Installation

```python
# nubia/internal/nubia.py  __init__
context._ctx = self._plugin.create_context()   # replaces the module-level None
self._ctx = context.get_context()
```

`get_context()` simply returns the module-level `_ctx` variable. There is no
lazy initialisation or thread-local storage; the single object is shared across
all threads in the process.

Plugins override `create_context()` to return a subclass of `Context` that
carries additional application-specific state.

### Lifecycle hooks

These are called by the Nubia runtime at well-defined points. The base
implementation is a no-op; plugins override them by subclassing `Context`.

| Method | Signature | When called |
|---|---|---|
| `on_connected` | `async on_connected(*args, **kwargs)` | `react(Message.CONNECTED)` via event bus, i.e. when the `connect` command fires. |
| `on_interactive` | `async on_interactive(args)` | Just before the IOLoop starts reading input. `args` is the argparse Namespace. |
| `on_cli` | `async on_cli(cmd, args)` | Just before `run_cli` dispatches to a command. `cmd` is the command name string. |

`on_interactive` and `on_cli` are called directly from `nubia.py`; they bypass
the event bus. `on_connected` is reached through `Listener.react()`.

---

## CommandsRegistry

**File:** `nubia/internal/registry.py`

### Internal data structures

```python
_cmd_instance_map: dict[str, Command]   # lowercased name/alias → Command instance
_completer: WordCompleter               # prompt_toolkit completer, words list kept in sync
_listeners: list[Listener]             # ordered list; index 0 is highest priority
_parser: argparse._SubParsersAction    # argparse subparser action; passed to add_arguments
```

### register_command(cmd_instance, override=False)

```
1. cmd_instance.set_command_registry(self)   # back-reference
2. cmd_keys = cmd_instance.get_command_names()   # [primary_name] + aliases
3. check each cmd_key has a help string (reject silently with warning if not)
4. await cmd_instance.add_arguments(self._parser)
       # AutoCommand delegates to typing/argparse.register_command()
       # which calls _parser.add_parser(name, aliases=...) and then
       # adds each @argument as an argparse argument
5. if not override: check for name conflicts
6. if cmd_instance is a Listener: append to _listeners
7. for each name: _cmd_instance_map[name.lower()] = cmd_instance
                  _completer.words.append(name)
                  _completer.meta_dict[name] = short_help
8. for alias in get_cli_aliases(): _cmd_instance_map[alias.lower()] = cmd_instance
```

CLI aliases (step 8) are registered in `_cmd_instance_map` but are NOT added
to `_completer.words`. This keeps them out of interactive tab completion while
still making them resolvable in CLI mode.

### find_command(cmd)

```python
return _cmd_instance_map.get(cmd.lower())
```

Returns `None` if not found. Callers are responsible for handling `None`.

### Listener priority

`register_priority_listener()` inserts at index 0 (head of list).
`register_listener()` appends to the tail.

`Context` is always registered at index 0 (`register_priority_listener(ctx)` in
`_pre_run`). Plugin-supplied listeners are appended via the constructor loop.
IOLoop registers itself as a listener when it constructs (`register_listener(self)`).

### dispatch_message(msg, *args, **kwargs)

Iterates `_listeners` in order, calling `await try_await(mod.react(msg, ...))`.
`try_await` handles both synchronous and coroutine return values transparently.
Exceptions inside `react()` are caught and logged by `Listener.react()` (see
Event Bus). Iteration continues even if one listener fails.

---

## Event Bus

**File:** `nubia/internal/io/eventbus.py`

### Message values

```python
class Message:
    CONNECTED = 1
```

Currently only one message type exists. Adding new messages requires extending
this class and implementing corresponding handling in `Listener.react()`.

### Listener base class

```python
class Listener:
    async def react(self, msg, *args, **kwargs):
        if msg == Message.CONNECTED:
            try:
                await try_await(self.on_connected(*args, **kwargs))
            except NotImplementedError:
                raise
            except Exception as e:
                logger.info("Couldn't initialize {}: {}".format(type(self), e))
                traceback.print_exc()

    async def on_connected(*args, **kwargs):
        raise NotImplementedError(...)
```

Subclasses must implement `on_connected`. Any exception other than
`NotImplementedError` is caught, logged, and swallowed; the listener is not
removed from the list.

`Context` extends `Listener` and overrides `on_connected` as a no-op (the
base implementation does nothing; plugin subclasses add real logic).
`IOLoop` extends `Listener` and overrides `on_connected` as a no-op.
Command objects that extend `Listener` receive `CONNECTED` when a connect event fires.

### When CONNECTED fires

The `connect` builtin command (`nubia/internal/commands/builtin.py`) calls
`registry.dispatch_message(Message.CONNECTED, ...)` after a successful
connection. All registered listeners receive the message in priority order.

---

## Component interactions

```
Nubia._pre_run()
  │
  ├─ creates CommandsRegistry
  │       │
  │       └─ _listeners[]  ←── register_priority_listener(ctx)
  │                        ←── register_listener(IOLoop)
  │                        ←── listener instances from plugin
  │
  ├─ ctx.set_registry(registry)
  │       # Context now holds a reference to the registry
  │       # Commands can call context.get_context().registry to reach it
  │
  └─ registry.register_command(cmd)
          # if cmd is a Listener: also appended to _listeners

At runtime:

  IOLoop.evaluate_command()
    → registry.find_command(name)       # lookup in _cmd_instance_map
    → cmd_instance.run_interactive()
        → context.get_context().cmd = name     # update ctx state
        → fn(**args)

  builtin.Connect.run_interactive()
    → registry.dispatch_message(Message.CONNECTED)
        → for listener in _listeners:
              listener.react(CONNECTED)
                  → listener.on_connected()    # ctx.on_connected(), IOLoop.on_connected(), ...
```

The context does not dispatch messages; it only receives them. The registry is
the sole dispatcher. The context is the only object that holds a reference to
the registry at the module level (via `get_context().registry`), providing a
single entry point for commands that need to inspect registered commands at
runtime.
