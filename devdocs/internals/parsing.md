# Parsing

Nubia has two independent parsing subsystems: a pyparsing grammar for
interactive mode and argparse integration for CLI mode. Completion has its own
partial-parse state machine that sits on top of the interactive grammar.

---

## Interactive Parser

**File:** `nubia/internal/parser.py`

### Grammar

The grammar is defined as module-level pyparsing expressions and compiled once
at import time.

#### Primitives

```python
identifier      = Word(alphas + "_-", alphanums + "_-")
int_value       = Regex(r"\-?\d+")           → int
float_value     = Regex(r"\-?\d+\.\d*([eE]\d+)?")  → float
bool_value      = Literal("True"|"true"|"False"|"false")  → bool
quoted_string   = quotedString                → str (quotes stripped)
unquoted_string = Word(alphanums + r"-_/#@£$€%*+~|<>?.:") → str
string_value    = quoted_string | unquoted_string
single_value    = bool_value | string_value | float_value | int_value
```

#### Composite values

```python
list_value  = "[" delimitedList(single_value) "]"    → Python list
dict_value  = "{" delimitedList(key: value pairs) "}" → Python dict (recursive)
value       = list_value ^ single_value ^ dict_value
```

`dict_value` is defined with `pp.Forward()` so it can appear as a value inside
another dict.

#### Top-level grammar forms

```python
key_value   = Dict(ZeroOrMore(Group(identifier + "=" + value)))
              .setResultsName("kv")

positionals = ZeroOrMore(single_value + NotAny("="))
              .setResultsName("positionals")
# NotAny("=") ensures "something=" is not parsed as positional "something"

subcommand  = identifier.setResultsName("__subcommand__")

command_with_subcommand = Optional(subcommand) + positionals + key_value
command                 = positionals + key_value
```

`parse(text, expect_subcommand)` selects between these two top-level forms.

### Supported syntax

```
# positional arguments (bare values)
show-routes 10.0.0.0 255.255.255.0

# keyword arguments
show-routes prefix=10.0.0.0 mask=255.255.255.0

# list value
filter states=[up,down]

# dict value (semicolon-separated key:value inside braces)
config params={timeout:30;retry:3}

# super-command with sub-command
interface show name=eth0
#          ^^^^ sub-command name
```

### Type transforms

Each parse action calls one of:

| Type | Transform |
|---|---|
| `int` | `int(x)` |
| `float` | `float(x)` |
| `bool` | `x in ["True", "true"]` |
| `str` | strips surrounding `"` or `'` |
| `list` | Python list (via pyparsing `Group`) |
| `dict` | `dict()` on the pyparsing result |

### CommandParseError

Defined in `nubia/internal/exceptions.py`. Raised by `parser.parse()` when
pyparsing raises `ParseException`.

Additional attributes set on the exception before re-raising:

| Attribute | Content |
|---|---|
| `remaining` | substring of the input after the parse failure position (extracted from `markInputline()` output) |
| `partial_result` | `ParseResults` from a non-strict parse up to the failure point |
| `col` | column number of the failure |

`AutoCommand.run_interactive` catches `CommandParseError` and prints the
offending position using `e.col` to align a caret under the bad token.
`AutoCommandCompletion.get_completions` catches it and uses `partial_result`
and `remaining` to continue generating completions on partial input.

### split_command()

**File:** `nubia/internal/interactive.py:34`

```python
def split_command(text):
    return text.lstrip(" ").split(" ", 1)
```

Splits on the first space only. Returns a one-element list if there is no
space (command name with no arguments), or a two-element list
`[command_name, args_string]`. The `args_string` is then passed verbatim to
`parser.parse()` inside `AutoCommand.run_interactive`.

---

## CLI Parser (argparse integration)

**File:** `nubia/internal/typing/argparse.py`

### Subparser structure

```
opts_parser (ArgumentParser)           # global flags: --verbose, --stderr, etc.
  └─ cmd_parser (_SubParsersAction, dest="_cmd")
       ├─ connect (SubParser)          # built-in: enters interactive mode
       ├─ exit    (SubParser)
       ├─ help    (SubParser)
       └─ <user command> (SubParser)
            └─ optional sub-commands (_SubParsersAction, dest="_subcmd")
                 └─ <subcommand> (SubParser)
```

`SubParser` (created by `create_subparser_class`) copies global flags from the
main parser into each subcommand parser. This allows global flags like
`--verbose` to appear after the subcommand name on the command line.

### How annotations become argparse arguments

`_argument_to_argparse_input(arg)` converts an `Argument` namedtuple to the
`*args, **kwargs` form needed by `parser.add_argument()`:

| Python type | argparse translation |
|---|---|
| `int` | `type=int, metavar="INT"` |
| `float` | `type=float, metavar="FLOAT"` |
| `str` | `type=str, metavar="STR"` |
| `bool` (or `default=False`) | `action="store_true"` |
| `bool` with `default=True` | `action="store_false"` |
| `Optional[T]` | unwrapped to `T` first |
| `List[T]` | `type=T, nargs="+"` |
| `Dict[K, V]` | `type=_parse_dict(...)` (custom callable) |
| other | `type=argument_type` (passed through) |

For `nargs=-1` (set via `@argument(..., nargs=-1)`): argparse `nargs="+"` is
used, and a join function is injected as `type` when the annotation is `str`.

### Argument name transformation

`transform_argument_name(name)` — `argparse.py:302`:

- single-character names → `-x` (single dash)
- multi-character names → `--name` (double dash)
- underscores in names are converted to hyphens by `transform_name()`

### Aliases as argparse alternatives

```python
add_argument_args = [
    transform_argument_name(x) for x in ([arg.name] + arg.extra_names)
]
```

All aliases are passed as the positional `*args` to `add_argument`, making
them equivalent flags. For example `["--count", "-c"]`.

Aliases are not supported for positional arguments (raises `ValueError`).

### Positional vs keyword arguments

If `arg.positional` is `True`:
- `add_argument_args = [arg.name]` (no leading dashes)
- Default values are not supported (raises `ValueError`)
- Aliases are not supported

If `arg.positional` is `False` (default):
- `add_argument_args = ["--name", ...]`
- `required = not arg.default_value_set`
- `default = arg.default_value`

### Super-command subparser registration

`register_command` recursively calls itself when `inspection.subcommands` is
non-empty:

```python
subcommand_parsers = subparser.add_subparsers(dest="_subcmd", ...)
subcommand_parsers.required = True
for _, v in inspection.subcommands:
    register_command(subcommand_parsers, v)
```

`args._subcmd` is then used in `AutoCommand.run_cli` to dispatch to the correct
bound method.

### Mutually exclusive arguments

`@command(exclusive_arguments=[["arg_a", "arg_b"]])` causes those arguments to
be placed in an `argparse.add_mutually_exclusive_group()` rather than added
directly to the subparser.

---

## Completion State Machine

**File:** `nubia/internal/completion.py`

### ShellCompleter dispatch

`ShellCompleter.get_completions()` (`interactive.py:182`) is the entry point
called by prompt_toolkit on every keystroke:

```
text_before_cursor
  ├─ one word  → registry._completer.get_completions()   # suggest command names
  └─ two+ words → cmd_instance.get_completions(cmd, sub_document, event)
                    ├─ super_command and first word only → _commands_completer
                    └─ otherwise → AutoCommandCompletion(self, doc, event)
```

### AutoCommandCompletion

Instantiated fresh on each completion request. It holds:

- `self.doc` — the `Document` for the args portion (after the command name)
- `self.cmd` — the `AutoCommand` instance
- `self.meta` — `cmd.metadata` (`FunctionInspection`)

#### get_completions()

```
1. Fix "keyword= " space bug:
       if char_before_cursor != " " and "= " found in text:
           remove the space after "=" from the document text

2. Try parser.parse(doc.text, expect_subcommand=...)
       on ParseError: partial_result = e.partial_result
                      remaining     = e.remaining

3. Determine last_token:
       if char_before_cursor in " ]}":  last_token = ""
       else:                            last_token = text from last space to cursor

4. if remaining is longer than last_token: last_token = remaining

5. _prepare_args_completions(parsed, last_token)
```

#### _prepare_args_completions()

```
if super_command:
    subcommand = parsed["__subcommand__"]
    args_meta = chain(cmd_args, subcommand_args)

args_meta = _filter_arguments_by_prefix(last_token, args_meta)
parsed_keys = parsed.asDict().get("kv", [])   # already-supplied keys
parsed_token = TokenParse(last_token)

if parsed_token.is_positional:
    # positional completion not yet implemented; returns []

elif parsed_token.is_argument:
    arg = _find_argument_by_name(parsed_token.argument_name)
    if arg.choices is Callable:
        choices = arg.choices(cmd_name, subcommand, last_token, doc.text)
    else:
        choices = [c for c in arg.choices if str(c).startswith(last_value)]
    return [Completion(str(choice), start_position=-len(last_value)) ...]

else:
    # completing an argument name
    return [Completion(arg.name + "=", start_position=-len(last_token), ...)
            for arg in args_meta if arg.name not in parsed_keys]
```

Completions are capped at `options.limit_visible_choices`.

### TokenParse

Dissects a single partial token (e.g. `"state=up"`, `"state="`, `"state=[up"`).

```python
token.partition("=")
# key, "=", value
```

| Property | Meaning |
|---|---|
| `is_argument` | `"="` was present |
| `is_positional` | no `"="` |
| `is_list` | value starts with `[` |
| `is_dict` | value starts with `{` |
| `is_single_value` | neither list nor dict |
| `argument_name` | key part before `=` |
| `last_value` | for lists: text after last `,`; for scalars: full value |

`last_value` is used as the prefix filter when matching static choices.

### Completion sources

| Source | Condition | Implementation |
|---|---|---|
| Command names | cursor in first word | `registry._completer` (WordCompleter) |
| Sub-command names | super_command, cursor in first word of args | `cmd._commands_completer` (WordCompleter) |
| Argument names | cursor at key position | constructed from `args_meta`, appended with `=` |
| Static value choices | `arg.choices` is a list | filtered by `last_value` prefix |
| Dynamic value choices | `arg.choices` is callable | called with `(cmd_name, subcommand, last_token, full_text)`, must return `List[str]` |

Dynamic choice callables must return a `list`; a non-list return raises
`ValueError` in `get_completions`.
