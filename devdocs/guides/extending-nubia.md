# Extending Nubia

This guide explains how to customize Nubia's behavior by subclassing its extension
points: `PluginInterface`, `Context`, `StatusBar`, and `Listener`.

The `example/` directory contains a complete working implementation of every extension
point described here.

---

## Writing a Plugin

`PluginInterface` is the central customization hook. Create one subclass per application
and pass an instance to `Nubia`.

```python
# myapp_plugin.py
import argparse
from nubia import PluginInterface
from myapp_context import MyAppContext
from myapp_statusbar import MyAppStatusBar


class MyAppPlugin(PluginInterface):
    """
    Application-specific plugin. Override only the methods you need.
    """

    def create_context(self):
        # Return your custom Context subclass (see below).
        return MyAppContext()

    def validate_args(self, args):
        # Called after argparse runs. Raise ArgsValidationError on bad input.
        # args is the Namespace returned by get_opts_parser().parse_args().
        pass

    def get_opts_parser(self, add_help=True):
        # Add application-level CLI flags here.
        parser = argparse.ArgumentParser(
            description="My App",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            add_help=add_help,
        )
        parser.add_argument("--config", "-c", default="", type=str,
                            help="Path to config file")
        parser.add_argument("--verbose", "-v", action="count", default=0,
                            help="Increase verbosity")
        return parser

    def get_status_bar(self, context):
        return MyAppStatusBar(context)

    def get_listeners(self):
        # Return class objects (not instances). Nubia instantiates them.
        return []

    def create_usage_logger(self, context):
        # Return a UsageLoggerInterface subclass instance, or None.
        return None
```

Wire the plugin into the shell in your entry point:

```python
# myapp.py
import sys
import commands
from nubia import Nubia, Options
from myapp_plugin import MyAppPlugin

if __name__ == "__main__":
    shell = Nubia(
        name="myapp",
        command_pkgs=commands,
        plugin=MyAppPlugin(),
        options=Options(persistent_history=False),
    )
    sys.exit(shell.run())
```

### Methods to Override

| Method | When to override |
|---|---|
| `create_context()` | Always — return your `Context` subclass |
| `get_opts_parser()` | When you need app-specific CLI flags |
| `validate_args(args)` | When flags require cross-validation or context initialization |
| `get_status_bar(context)` | When you want a custom bottom toolbar |
| `get_listeners()` | When you need objects that react to shell lifecycle events |
| `getBlacklistPlugin()` | When certain commands should be blocked at runtime |
| `get_completion_datasource_for_global_argument(arg)` | Tab-completion for global flags |
| `setup_logging(root_logger, args)` | Custom logging configuration |
| `create_usage_logger(context)` | Usage telemetry |
| `get_session_logger(context)` | Session replay/logging |

See `nubia/internal/plugin_interface.py` for the full interface with default
implementations.

---

## Custom Context

`Context` holds per-session application state and provides lifecycle hooks. It is
available anywhere in a command via `context.get_context()`.

```python
# myapp_context.py
from nubia import context, eventbus, exceptions


class MyAppContext(context.Context):
    """
    Application context. Add fields for any state commands need to share.
    """

    def __init__(self):
        super().__init__()
        self._connection = None
        self.verbose = 0

    @property
    def connection(self):
        return self._connection

    async def on_interactive(self, args):
        """
        Called when the shell enters interactive mode.
        args is the argparse Namespace from get_opts_parser().
        """
        self.verbose = args.verbose
        # Run the connect command, then broadcast CONNECTED to all listeners.
        ret = await self._registry.find_command("connect").run_cli(args)
        if ret:
            raise exceptions.CommandError("Failed to connect")
        await self.registry.dispatch_message(eventbus.Message.CONNECTED)

    async def on_cli(self, cmd, args):
        """
        Called when a single command is executed from the CLI (non-interactive).
        """
        self.verbose = args.verbose
        await self.registry.dispatch_message(eventbus.Message.CONNECTED)

    async def on_connected(self, *args, **kwargs):
        """
        Called when CONNECTED is dispatched to listeners. Use for post-connect setup.
        """
        pass
```

Access the context from inside any command:

```python
from nubia import context

@command
def my_command():
    "Example using context"
    ctx = context.get_context()
    if ctx.verbose:
        print("Verbose mode is on")
```

### Lifecycle Hook Summary

| Hook | Triggered when |
|---|---|
| `on_interactive(args)` | Shell starts in interactive (REPL) mode |
| `on_cli(cmd, args)` | Shell runs a single command from `sys.argv` |
| `on_connected(*args, **kwargs)` | `eventbus.Message.CONNECTED` is dispatched |

`on_interactive` and `on_cli` are the right place to initialize connections, set
verbosity from `args`, and dispatch `CONNECTED` to listeners.

---

## Custom Status Bar

`StatusBar` controls the bottom toolbar and right-side prompt shown in interactive mode.
It is rendered by prompt-toolkit.

```python
# myapp_statusbar.py
from pygments.token import Token
from nubia import context, statusbar


class MyAppStatusBar(statusbar.StatusBar):
    def __init__(self, ctx):
        self._last_status = None

    def get_tokens(self):
        """
        Returns a list of (Token, str) pairs for the bottom toolbar.
        Token types are styled via prompt-toolkit's pygments integration.
        """
        spacer = (Token.Spacer, "  ")
        verbose = context.get_context().verbose
        verb_token = (Token.Warn, "ON") if verbose else (Token.Info, "OFF")
        return [
            (Token.Toolbar, "MyApp"),
            spacer,
            (Token.Toolbar, "Verbose "),
            verb_token,
        ]

    def get_rprompt_tokens(self):
        """
        Returns tokens shown on the right side of the input prompt.
        Useful for displaying the last command's exit status.
        """
        if self._last_status:
            return [(Token.RPrompt, f"Error: {self._last_status}")]
        return []

    def set_last_command_status(self, status):
        """
        Called by Nubia after each command completes. Store it for display.
        """
        self._last_status = status
```

Return the instance from your plugin:

```python
def get_status_bar(self, context):
    return MyAppStatusBar(context)
```

The base class (`nubia/internal/ui/statusbar.py`) provides no-op implementations of
all methods, so you only need to override what you use.

---

## Adding Event Listeners

Listeners respond to shell lifecycle events via the `eventbus` mechanism. The only
event currently defined is `Message.CONNECTED`.

```python
# myapp_listener.py
from nubia.internal.io import eventbus


class MyAppListener(eventbus.Listener):
    async def on_connected(self, *args, **kwargs):
        """
        Called when eventbus.Message.CONNECTED is dispatched.
        Perform any initialization that requires a live connection.
        """
        print("Listener: shell connected")
```

Return the class (not an instance) from your plugin. Nubia instantiates it:

```python
def get_listeners(self):
    return [MyAppListener]
```

`Context` itself subclasses `Listener`, so the context's `on_connected` is called
automatically without explicitly listing it here.

---

## Custom Argument Validation

`validate_args` is called once at startup after the global options are parsed.

```python
def validate_args(self, args):
    """
    args: argparse.Namespace returned by get_opts_parser()
    Raise nubia.ArgsValidationError to abort startup with an error message.
    """
    from nubia import ArgsValidationError

    if args.config and not os.path.isfile(args.config):
        raise ArgsValidationError(f"Config file not found: {args.config}")

    # Optionally push values into the context here.
    ctx = context.get_context()
    ctx.config_path = args.config
```

This hook is the right place to check that required flags are present and consistent,
and to propagate parsed values into the context before any command runs.

---

## Global Options (argparse)

Override `get_opts_parser` to add flags that appear in the top-level `--help` and are
available to all commands via `context.args`.

```python
def get_opts_parser(self, add_help=True):
    parser = argparse.ArgumentParser(
        description="My Shell",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        add_help=add_help,
    )
    parser.add_argument("--config", "-c", default="", type=str,
                        help="Configuration file")
    parser.add_argument("--verbose", "-v", action="count", default=0,
                        help="Verbosity level")
    parser.add_argument("--stderr", "-s", action="store_true",
                        help="Send log output to stderr")
    return parser
```

The parsed result is stored in `context.args` and also passed to `on_interactive`,
`on_cli`, and `validate_args`.

To provide tab-completion for a global flag, implement
`get_completion_datasource_for_global_argument`:

```python
def get_completion_datasource_for_global_argument(self, argument):
    if argument == "--config":
        return MyConfigFileCompletionDataSource()
    return None
```

`CompletionDataSource.get_all()` must return a list of strings.
