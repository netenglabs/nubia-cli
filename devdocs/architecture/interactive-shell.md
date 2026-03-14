# Interactive Shell Architecture

**Source files:** `nubia/internal/interactive.py`, `nubia/internal/completion.py`, `nubia/internal/ui/lexer.py`, `nubia/internal/ui/style.py`

---

## IOLoop: The REPL Engine

`IOLoop` (in `nubia/internal/interactive.py`) is the main read-eval-print loop. It subclasses `Listener` so it can receive event-bus messages from the command registry. It is instantiated by `Nubia._create_interactive_io_loop()` and owned for the lifetime of the interactive session.

Constructor arguments:

```python
IOLoop(context, plugin, usagelogger, options: Options)
```

On construction it:
- Pulls the `CommandsRegistry` from the context.
- Calls `plugin.getBlacklistPlugin()` and `plugin.get_status_bar(context)` to wire up blacklisting and the bottom toolbar.
- Creates a `ShellCompleter` bound to the registry.
- Registers itself as a listener on the registry (`register_listener(self)`).

---

## Building the PromptSession

`IOLoop._build_cli()` assembles the `prompt_toolkit.PromptSession` object each time `run()` is called.

**History:** Controlled by `Options.persistent_history`.
- `True` (default): `FileHistory` stored at `~/.{binary_name}_history`.
- `False`: `InMemoryHistory` — history is lost on exit.

**Editing mode:** Read from the `EDITOR` environment variable and mapped to `prompt_toolkit.enums.EditingMode`. If the variable is absent or unrecognised, EMACS keybindings are used.

**PromptSession options assembled:**

| Parameter | Value |
|---|---|
| `history` | `FileHistory` or `InMemoryHistory` |
| `auto_suggest` | `AutoSuggestFromHistory()` |
| `lexer` | `PygmentsLexer(NubiaLexer)` |
| `completer` | `ShellCompleter(registry)` |
| `input_processors` | `[HighlightMatchingBracketProcessor("[](){}")]` |
| `style` | `shell_style` (Monokai-based, see below) |
| `bottom_toolbar` | `IOLoop._get_bottom_toolbar` callable |
| `editing_mode` | Derived from `$EDITOR` |
| `complete_in_thread` | `True` |
| `refresh_interval` | 1 second |

The prompt text itself comes from `plugin.get_prompt_tokens(context)`, which by default delegates to `context.get_prompt_tokens()`. The right-side prompt comes from `status_bar.get_rprompt_tokens()`. Both are rendered as `PygmentsTokens` lists.

---

## Command Evaluation Flow

```
IOLoop.run()
  └─ prompt.prompt_async()          # blocks until user presses Enter
       └─ IOLoop.parse_and_evaluate(text)
            └─ split_command(text)  # text.lstrip().split(" ", 1)
                 # yields [cmd] or [cmd, args_string]
            └─ IOLoop.evaluate_command(cmd, args, raw)
                 ├─ registry.find_command(cmd)  # exact match
                 │    # if not found: find_approx() for fuzzy suggestions
                 │    # if auto_execute_single_suggestions and one match: auto-correct
                 ├─ blacklist.is_blacklisted(cmd)  # abort if non-zero
                 ├─ usagelogger.pre_exec()
                 ├─ cmd_instance.run_interactive(cmd, args, raw)  # awaited
                 ├─ usagelogger.post_exec(cmd, args, result, False)
                 └─ status_bar.set_last_command_status(result)
```

`split_command` is a module-level function that strips leading spaces and splits on the first space only, yielding at most `[command_name, remaining_args_string]`.

`evaluate_command` handles three resolution cases for an unknown command name:
1. Single fuzzy match + `auto_execute_single_suggestions=True` → auto-correct and execute.
2. Multiple fuzzy matches → print suggestion list, do nothing.
3. No match → print "Unknown Command" message.

`KeyboardInterrupt` inside the prompt loop is caught and silently ignored (equivalent to Ctrl-C clearing the line). `EOFError` (Ctrl-D) exits the loop cleanly.

---

## Stdin (Non-TTY) Mode

Before entering the REPL, `Nubia.start_interactive()` checks `sys.stdin.isatty()`.

If stdin is not a TTY (e.g., piped input or a script):
```python
commands = sys.stdin.readlines()
for command in commands:
    print("> {}".format(command))
    ret = await io_loop.parse_and_evaluate(command)
    if ret:
        return ret   # stop on first failure
```

The same `IOLoop.parse_and_evaluate()` path is used, so blacklisting, usage logging, and status bar updates all apply. No `PromptSession` is created in this path — `_build_cli()` is never called.

---

## ShellCompleter

`ShellCompleter` (also in `interactive.py`) wraps the registry to provide top-level completions and delegates to per-command completers for argument completions.

```python
class ShellCompleter(Completer):
    def get_completions(self, document, complete_event):
        if document.on_first_line:
            cmd_and_args = split_command(document.text_before_cursor)
            if len(cmd_and_args) > 1:
                cmd, args = cmd_and_args
                cmd_instance = self._command_registry.find_command(cmd)
                if not cmd_instance:
                    return []
                return cmd_instance.get_completions(cmd, Document(args, ...), complete_event)
            else:
                return self._command_registry.get_completions(document, complete_event)
        return []
```

Two cases:
- **Cursor is still on the first word** (no space yet): delegate to `registry.get_completions()` which returns matching command names.
- **Cursor is past the first word**: find the command by exact name, then call `cmd_instance.get_completions()` which eventually reaches `AutoCommandCompletion`.

Completions are only offered on the first line of the document. Multi-line input never triggers completions.

---

## AutoCommandCompletion State Machine

`AutoCommandCompletion` (in `nubia/internal/completion.py`) is the completion engine for a single `AutoCommand`. It is constructed fresh for each completion request.

```python
AutoCommandCompletion(cmd_obj, document, complete_event)
```

`get_completions()` runs the following pipeline:

1. **Space-after-`=` fixup.** If the cursor is not on a space and `"= "` appears before it, the extra space is removed from the document text in-place. This prevents the parser from mis-classifying `key= ` (with trailing space) as a complete token.

2. **Parse the current input.** `parser.parse(doc.text, expect_subcommand=cmd.super_command)` is called. On failure, the partial result and the unparsed `remaining` string are retained.

3. **Determine `last_token`.** The last whitespace-delimited token before the cursor. If the partial-parse `remaining` string is longer, it is used instead (handles open lists/dicts that contain spaces).

4. **Dispatch to `_prepare_args_completions()`.**

### Inside `_prepare_args_completions`

- If the command is a super-command, the subcommand name is extracted from `parsed["__subcommand__"]` and its argument metadata is chained with the super-command's metadata.
- `last_token` is analyzed with `TokenParse` (see below).

**`TokenParse`** parses a raw token string like `state=up` or `ports=[eth0,`:
- Splits on first `=` to detect key=value vs. positional.
- If value starts with `[`, marks it as a list and extracts the last comma-separated element as `last_value`.
- If value starts with `{`, marks it as a dict.
- Otherwise, `last_value` is the whole value string.

**Completion type selection:**

| Condition | What is completed |
|---|---|
| `parsed_token.is_positional` | Positional argument values (not yet implemented; placeholder only) |
| `parsed_token.is_argument` and `arg.choices` is `Callable` | Dynamic choices: call `arg.choices(cmd_name, subcommand, last_token, doc.text)` — must return `List[str]` |
| `parsed_token.is_argument` and `arg.choices` is a list | Filter the static list by `last_value` prefix |
| Neither (completing argument names) | Emit `"name="` completions for all arguments not already in the parsed key-value set |

The number of visible completions is capped at `Options.limit_visible_choices` (default 10).

Completion display metadata (shown next to each suggestion) is built by `_get_arg_help()`: `[type, default: X]` or `[type, required]` plus the argument's description string.

---

## NubiaLexer

`NubiaLexer` (in `nubia/internal/ui/lexer.py`) is a Pygments `RegexLexer` that provides syntax highlighting for the interactive prompt.

It has two states:

**`root` state** (normal command input):

| Pattern | Token | Notes |
|---|---|---|
| `^SELECT\s` | `Name.Command` | Switches lexer to `query` state |
| `^(? or help)$` | `Name.Help` | |
| `^(q or quit or exit)$` | `Name.Exit` | |
| `identifier=` | `Name.Key`, `Operator` | Argument key-value syntax |
| Command with subcommand | dispatched to `command_callback` | |
| Bare command | dispatched to `command_callback` | |
| Boolean literals | `Keyword` | |
| Integers | `Number.Integer` | |
| Single/double-quoted strings | `String.Single` / `String.Symbol` | |
| Punctuation `; : ( ) [ ] , .` | `Punctuation` | |

**`command_callback`** is a dynamic callback (not a static token). It looks up the command name in the live `context.registry`:
- Valid command → `Name.Command` (rendered in amber `#f2b44f`).
- Invalid command → `Name.InvalidCommand` (rendered with red background).
- For super-commands: the subcommand word gets `Name.SubCommand` if valid, `Name.Symbol` if it looks like a positional.

**`query` state** handles SQL-like input after a `SELECT` keyword, applying standard SQL keyword, type, and operator tokens.

---

## Shell Style

`shell_style` (in `nubia/internal/ui/style.py`) merges three layers using `prompt_toolkit.styles.merge_styles`:

1. **MonokaiStyle** from Pygments — base theme.
2. A `style_from_pygments_dict` mapping custom token types to hex colors:
   - `Name.Command` → `#f2b44f` (amber)
   - `Name.SubCommand` → `#f2c46f` (lighter amber)
   - `Name.InvalidCommand` → red background, black text
   - `Token.RPrompt` → red background (used for error display)
   - `Token.Toolbar` / `Token.Spacer` → dark toolbar background
   - Alarm severity tokens (`MinorAlarm`, `MajorAlarm`, `CriticalAlarm`) → blue/orange/red
   - `Token.Good` / `Token.Bad` / `Token.Info` / `Token.Warn` → green/red/blue/yellow backgrounds
3. A `Style.from_dict` override forcing the bottom toolbar background to `#1c1c1c`.

To restyle the shell, modify the `style_from_pygments_dict` entries or add additional merge layers. Do not replace `shell_style` wholesale — the Monokai base handles all Pygments token types not explicitly overridden.

---

## Options That Affect Interactive Behavior

These are fields on the `Options` dataclass (`nubia/internal/options.py`), passed to `Nubia()` at construction:

| Option | Type | Default | Effect |
|---|---|---|---|
| `persistent_history` | `bool` | `True` | Use `FileHistory` at `~/.{name}_history` vs. `InMemoryHistory` |
| `auto_execute_single_suggestions` | `bool` | `True` | When an unknown command has exactly one fuzzy match, auto-correct and run it without asking |
| `limit_visible_choices` | `int` | `10` | Cap on completions shown in the popup; all are available but only this many render |

```python
from nubia import Nubia
from nubia.internal.options import Options

shell = Nubia(
    name="myshell",
    plugin=MyPlugin(),
    options=Options(
        persistent_history=False,
        auto_execute_single_suggestions=False,
        limit_visible_choices=20,
    ),
)
```

---

## IPython Integration

When `Nubia.run(ipython=True)` is called, `start_interactive()` is skipped and `start_ipython()` is called instead, which delegates to `nubia/internal/ipython.py`.

`start_interactive_python()` does the following:

1. Calls `ctx.on_interactive(args)`.
2. Iterates over all registered commands. For each `AutoCommand`, calls `cmd._get_executable_function()` and injects the result into `custom_locals` under the command's name (with `-` replaced by `_`). This makes every command callable as a plain Python function in the IPython namespace.
3. Configures `IPython.terminal.embed.InteractiveShellEmbed` with:
   - `cfg.TerminalInteractiveShell.prompts_class = NubiaPrompt` (custom prompt from `nubia/internal/ui/ipython.py`)
   - `autocall = 2` (call functions without parentheses)
   - `autoawait = True` (allow `await` at the top level)
4. Calls `plugin.update_ipython_kwargs(ctx, kwargs)` to allow the plugin to inject additional `InteractiveShellEmbed` constructor arguments.
5. Registers any magic classes returned by `plugin.get_magics()` via `ipshell.register_magics()`.

**`plugin.get_magics()`** should return a list of classes (not instances) that inherit from `IPython.core.magic.Magics`. These are registered verbatim with the embedded shell.

**`plugin.update_ipython_kwargs(ctx, kwargs)`** receives the mutable `kwargs` dict before the shell is constructed. Modify it in-place to override banner text, add user namespace entries, or change any other `InteractiveShellEmbed` parameter.
