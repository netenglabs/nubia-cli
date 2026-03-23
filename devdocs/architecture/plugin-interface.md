# Plugin Interface Architecture

**Source files:** `nubia/internal/plugin_interface.py`, `nubia/internal/context.py`, `nubia/internal/options.py`, `nubia/internal/blackcmd.py`, `nubia/internal/ui/statusbar.py`, `example/nubia_plugin.py`, `example/nubia_statusbar.py`, `example/nubia_context.py`

---

## Overview

The `PluginInterface` class is the primary extension point for a Nubia-based shell. A single plugin instance is passed to the `Nubia` constructor and queried at startup and at runtime to configure every customizable aspect of the shell: context, logging, argument parsing, command sets, status bar, blacklisting, and usage tracking.

All methods have default implementations. Override only what you need.

```python
from nubia import Nubia, PluginInterface

class MyPlugin(PluginInterface):
    ...

shell = Nubia(name="myshell", plugin=MyPlugin())
shell.run()
```

---

## PluginInterface Hook Methods

### `create_context() -> Context`

Called once during `Nubia.__init__()`. The returned object becomes the global singleton accessible via `nubia.context.get_context()`.

Must return an instance of a class that inherits from `nubia.internal.context.Context`. The default implementation returns a bare `Context()`.

```python
def create_context(self):
    return MyAppContext()
```

### `validate_args(args) -> None`

Called after argument parsing, before any command runs. `args` is the `argparse.Namespace` produced by the parser returned from `get_opts_parser()`.

Raise `nubia.internal.exceptions.ArgsValidationError` to abort startup with an error message. Any other exception is also caught and printed, but the shell continues.

```python
def validate_args(self, args):
    if not args.config:
        raise ArgsValidationError("--config is required")
```

### `get_commands() -> list`

Called during `Nubia._pre_run()`. Return a list of instantiated `Command` (or `AutoCommand`) objects to register alongside the commands loaded from `command_pkgs`. Commands returned here are registered with `override=True`, so they can replace built-ins.

```python
def get_commands(self):
    return [MySpecialCommand()]
```

### `get_listeners() -> list`

Return a list of classes (not instances) that implement `nubia.internal.io.eventbus.Listener`. Nubia instantiates them and passes them to `CommandsRegistry`. The default returns an empty list.

Note: the docstring says "classes", not instances. Pass the class object itself.

### `get_opts_parser(add_help=True) -> argparse.ArgumentParser`

Called at the start of `_pre_run()`. Return an `ArgumentParser` that defines the global CLI flags for your shell. Nubia will add subparsers to this parser for each registered command.

The default implementation adds `--verbose`/`-v`, `--stderr`/`-s`, and `--command-timeout`.

```python
def get_opts_parser(self, add_help=True):
    parser = argparse.ArgumentParser(
        description="My Shell",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=add_help,
    )
    parser.add_argument("--config", "-c", default="", type=str)
    parser.add_argument("--verbose", "-v", action="count", default=0)
    parser.add_argument("--stderr", "-s", action="store_true")
    return parser
```

Always pass `add_help=add_help` through to `ArgumentParser` — Nubia calls `get_opts_parser(add_help=False)` when building sub-parser models.

### `get_status_bar(context) -> StatusBar`

Called during `IOLoop.__init__()`. Return a `StatusBar` instance (see the StatusBar section below). The default returns a no-op `StatusBar`.

### `get_prompt_tokens(context) -> List[Tuple[Any, str]]`

Called on every prompt render. Return a list of `(pygments_token, text)` tuples that form the left-side prompt. The default delegates to `context.get_prompt_tokens()`.

Override here if you want the prompt shape to be entirely controlled by the plugin rather than the context. Override `context.get_prompt_tokens()` if you want the context object to own the prompt.

### `setup_logging(root_logger, args) -> None`

Called after argument parsing. `root_logger` is `logging.root`. If you return a truthy value, Nubia's default logging setup (tempfile or stderr based on `--stderr`) is skipped entirely. If you return `None` (the default), Nubia configures logging based on `--verbose` and `--stderr`.

```python
def setup_logging(self, root_logger, args):
    logging.basicConfig(level=logging.WARNING)
    return root_logger  # non-None skips Nubia's default setup
```

### `create_usage_logger(context) -> UsageLoggerInterface | None`

Called lazily on first command execution. Return an instance of a class implementing `nubia.internal.usage_logger_interface.UsageLoggerInterface`. If `None` is returned, a no-op `UsageLoggerInterface` is used.

The interface requires `pre_exec()` and `post_exec(cmd, args, result, is_cli)` methods.

### `getBlacklistPlugin() -> CommandBlacklist`

Called during `Nubia.__init__()` and `IOLoop.__init__()`. Return a `CommandBlacklist` instance (see below). The default returns an empty `CommandBlacklist` that blocks nothing.

### `get_magics() -> list`

Used only in IPython mode. Return a list of classes (not instances) that inherit from `IPython.core.magic.Magics`. They are registered with the embedded IPython shell via `ipshell.register_magics()`.

### `update_ipython_kwargs(ctx, kwargs) -> None`

Called just before `InteractiveShellEmbed` is constructed in IPython mode. `kwargs` is the mutable dict of constructor arguments. Modify it in-place.

```python
def update_ipython_kwargs(self, ctx, kwargs):
    kwargs["banner1"] = "Welcome to MyShell"
    kwargs["user_ns"]["my_helper"] = some_object
```

### `get_completion_datasource_for_global_argument(name) -> CompletionDataSource | None`

Called when completing global CLI flags (the arguments defined in `get_opts_parser()`). `name` is the flag string, e.g. `"--config"`. Return a `CompletionDataSource` instance, or `None` to provide no completions for that flag.

```python
class ConfigFileCompletionDataSource(CompletionDataSource):
    def get_all(self):
        return ["/etc/myshell/prod.cfg", "/etc/myshell/staging.cfg"]

def get_completion_datasource_for_global_argument(self, name):
    if name == "--config":
        return ConfigFileCompletionDataSource()
    return None
```

### `get_session_logger(context) -> SessionLogger | None`

Called on each interactive command before evaluation. If non-`None`, the returned object's `log_command(text)` method is called with the raw input, and all output during command execution is captured via `session_logger.patch()` context manager. Return `None` (default) to disable session logging.

---

## StatusBar

**Source:** `nubia/internal/ui/statusbar.py`

`StatusBar` subclasses `eventbus.Listener`. An instance is held by `IOLoop` and queried on every prompt render.

```python
class StatusBar(eventbus.Listener):
    def __init__(self, context): ...
    def get_tokens(self) -> list: ...          # bottom toolbar content
    def get_rprompt_tokens(self) -> list: ...  # right-side prompt content
    def set_last_command_status(self, status): ...
    def start(self): ...
    def stop(self): ...
    async def on_connected(self, *args, **kwargs): ...
```

**`get_tokens()`** returns a list of `(pygments_token, text)` tuples rendered in the bottom toolbar. The toolbar is refreshed on the `refresh_interval` (1 second by default) via `prompt_toolkit`'s built-in refresh.

**`get_rprompt_tokens()`** returns tokens rendered right-aligned on the current input line. Used for per-command status (e.g., showing the last exit code).

**`set_last_command_status(status)`** is called by `IOLoop.evaluate_command()` after each command completes, passing the return value. Use this to cache the status for display in `get_rprompt_tokens()`.

**`start()` / `stop()`** are called at the beginning and end of `IOLoop.run()`. Use them to start/stop background threads that update toolbar data.

### Example StatusBar

From `example/nubia_statusbar.py`:

```python
from pygments.token import Token
from nubia import context, statusbar

class NubiaExampleStatusBar(statusbar.StatusBar):
    def __init__(self, context):
        self._last_status = None

    def get_rprompt_tokens(self):
        if self._last_status:
            return [(Token.RPrompt, "Error: {}".format(self._last_status))]
        return []

    def set_last_command_status(self, status):
        self._last_status = status

    def get_tokens(self):
        spacer = (Token.Spacer, "  ")
        is_verbose = (Token.Warn, "ON") if context.get_context().verbose else (Token.Info, "OFF")
        return [
            (Token.Toolbar, "Hello!"),
            spacer,
            (Token.Toolbar, "Verbose "),
            spacer,
            is_verbose,
        ]
```

The token types (`Token.Toolbar`, `Token.Spacer`, `Token.Warn`, `Token.Info`, `Token.RPrompt`) are styled in `nubia/internal/ui/style.py`. Add new token types there to give them colors.

---

## Context Customization

**Source:** `nubia/internal/context.py`

`Context` is the application-global state object. It is created by `plugin.create_context()`, stored in `context._ctx`, and retrieved anywhere via `nubia.context.get_context()`.

The base `Context` class provides:

| Member | Purpose |
|---|---|
| `binary_name` | The shell's name (set from `Nubia(name=...)`) |
| `registry` | The `CommandsRegistry` (set after commands are loaded) |
| `args` | The parsed `argparse.Namespace` (set after argument parsing) |
| `testing` | Boolean flag for test mode |
| `cmd` / `raw_cmd` | The command name and full raw string being executed |
| `isatty` | `os.isatty(sys.stdin.fileno())` |
| `get_prompt_tokens()` | Returns the default `[(Token.Username, user), ...]` prompt |
| `on_connected(*args, **kwargs)` | Async hook called when the shell connects |
| `on_interactive(args)` | Async hook called when interactive mode starts |
| `on_cli(cmd, args)` | Async hook called when a CLI (non-interactive) command runs |

All attribute access to `args`, `registry`, and `testing` is protected by an `RLock`.

### Extending Context

Subclass `Context` and add your own attributes. The example application adds `verbose`:

```python
# example/nubia_context.py
from nubia import context, eventbus, exceptions

class NubiaExampleContext(context.Context):
    async def on_cli(self, cmd, args):
        self.verbose = args.verbose
        await self.registry.dispatch_message(eventbus.Message.CONNECTED)

    async def on_interactive(self, args):
        self.verbose = args.verbose
        ret = await self._registry.find_command("connect").run_cli(args)
        if ret:
            raise exceptions.CommandError("Failed starting interactive mode")
        await self.registry.dispatch_message(eventbus.Message.CONNECTED)
```

Commands retrieve the context via:
```python
from nubia import context
ctx = context.get_context()
```

Since `get_context()` returns the same singleton, you can cast it to your subtype and access your custom fields.

---

## The Options Class

**Source:** `nubia/internal/options.py`

`Options` is a `dataclass` passed to `Nubia()`. It has no plugin hooks — it configures framework behavior directly.

```python
@dataclass
class Options:
    persistent_history: bool = True
    auto_execute_single_suggestions: bool = True
    limit_visible_choices: int = 10
```

| Field | Default | Effect |
|---|---|---|
| `persistent_history` | `True` | Persist command history to `~/.{name}_history` |
| `auto_execute_single_suggestions` | `True` | Auto-correct and run a command when there is exactly one fuzzy match |
| `limit_visible_choices` | `10` | Maximum completions shown in the dropdown |

Pass an `Options` instance to `Nubia`:

```python
shell = Nubia(name="myshell", plugin=MyPlugin(), options=Options(limit_visible_choices=20))
```

---

## Command Blacklisting

**Source:** `nubia/internal/blackcmd.py`

`CommandBlacklist` is a simple dict-backed guard checked by both `Nubia.run_cli()` and `IOLoop.evaluate_command()` before any command runs.

```python
class CommandBlacklist:
    _blacklisted_commands = {}

    def is_blacklisted(self, command):
        return command in self._blacklisted_commands

    def add_blocked_command(self, command):
        self._blacklisted_commands[command] = ""
```

`is_blacklisted(command)` returns the dict value (empty string, which is falsy) if the command is in the blacklist, and `False` otherwise. Any non-zero/non-falsy return from `is_blacklisted()` blocks execution and is returned as the command's exit code. The empty string `""` is falsy in Python, so the default `add_blocked_command` implementation effectively stores a falsy sentinel — to actually block execution, return a non-zero integer.

**To implement dynamic blacklisting**, subclass `CommandBlacklist` and override `is_blacklisted`:

```python
class MyBlacklist(CommandBlacklist):
    def is_blacklisted(self, command):
        if not is_connected():
            return 1   # non-zero blocks and is returned as exit code
        return 0
```

Return `0` or any falsy value to allow execution. Return a non-zero integer to block it.

Wire it into the plugin:

```python
def getBlacklistPlugin(self):
    bl = MyBlacklist()
    bl.add_blocked_command("dangerous-command")
    return bl
```

If `is_blacklisted()` raises an exception, the exception is caught, printed in red, and logged, but execution is allowed to proceed.

---

## Example Plugin Walkthrough

**Source:** `example/nubia_plugin.py`

The example plugin demonstrates the most common overrides:

```python
class NubiaExamplePlugin(PluginInterface):

    def create_context(self):
        return NubiaExampleContext()      # custom context with .verbose attribute

    def validate_args(self, args):
        pass                              # no validation needed

    def get_opts_parser(self, add_help=True):
        parser = argparse.ArgumentParser(
            description="Nubia Example Utility",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            add_help=add_help,
        )
        parser.add_argument("--config", "-c", default="", type=str)
        parser.add_argument("--verbose", "-v", action="count", default=0)
        parser.add_argument("--stderr", "-s", action="store_true")
        return parser

    def get_completion_datasource_for_global_argument(self, argument):
        if argument == "--config":
            return ConfigFileCompletionDataSource()
        return None

    def get_status_bar(self, context):
        return NubiaExampleStatusBar(context)

    def getBlacklistPlugin(self):
        blacklister = CommandBlacklist()
        blacklister.add_blocked_command("be-blocked")
        return blacklister

    def create_usage_logger(self, context):
        return None                       # no usage tracking


class ConfigFileCompletionDataSource(CompletionDataSource):
    def get_all(self):
        return ["/tmp/c1", "/tmp/c2"]
```

Key observations:
- `get_opts_parser()` does not call `super()` — it builds its own parser from scratch. This is the expected pattern; the base class parser is not a useful default for real applications.
- `get_completion_datasource_for_global_argument()` pairs with the `--config` flag to provide tab-completion for config file paths.
- The blacklist blocks the command named `"be-blocked"` by name. Since `add_blocked_command` stores `""` (falsy), `is_blacklisted("be-blocked")` returns `""` which is falsy — this means the command is technically not blocked by the default implementation. Override `is_blacklisted` and return a non-zero integer to actually block execution.
- `create_usage_logger()` returns `None`, causing Nubia to fall back to the no-op `UsageLoggerInterface`.
