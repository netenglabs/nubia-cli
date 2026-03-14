# Type System

This document describes how Nubia's decorators capture type metadata, how that metadata is used during interactive parsing and CLI argument registration, and how type conversion errors are surfaced.

## Decorators

`nubia/internal/typing/__init__.py`

### `@command`

```python
def command(name_or_function=None, help=None, aliases=None, exclusive_arguments=None):
```

Marks a function or class as a Nubia command.

**Parameters:**
- `name_or_function` — If a string, used as the command name. If omitted, the function name is transformed (`transform_name`) to kebab-case. When decorating a class, `transform_class_name` is used instead (CamelCase → kebab-case).
- `help` — Help string. Falls back to the function's docstring if `None`.
- `aliases` — Additional command names that resolve to this command. All aliases appear in `get_command_names()` and are registered in the `CommandsRegistry`.
- `exclusive_arguments` — Argument names that are mutually exclusive. Accepts either a flat list (one exclusive group) or a list of lists (multiple groups). Each group maps to an argparse `mutually_exclusive_group`. Validated at decoration time against the actual function parameters.

The decorator stores its data in `fn.__command` dict. The `__command` attribute is the presence check used by `cmdloader` to identify decorated objects.

The decorator supports two usage forms:

```python
@command                          # applied directly, name derived from function
@command("my-cmd", help="...")    # applied as a call
```

### `@argument`

```python
def argument(arg, type=None, description=None, name=None, aliases=None,
             positional=False, choices=None, nargs=1):
```

Annotates a single parameter of a `@command`-decorated function with metadata.

**Parameters:**
- `arg` — The Python parameter name as a string. Must match an actual parameter in the function signature (or the function must accept `**kwargs`).
- `type` — The Python type for this argument. If the function already has a PEP 484 annotation for the same parameter, the two must agree or a `TypeError` is raised. If `None`, falls back to the annotation from the function signature.
- `description` — Help text shown in CLI `--help` output.
- `name` — Display name used in interactive mode and as the argparse flag (after `transform_name`). Defaults to `transform_name(arg)` (underscores become dashes, leading/trailing underscores stripped).
- `aliases` — Alternative names accepted in interactive mode and as argparse flags. Single-character aliases become single-dash flags (`-f`); longer aliases become double-dash flags (`--flag`). Not supported for positional arguments.
- `positional` — If `True`, the argument may be supplied positionally in interactive mode (without a key name). Not supported on class-level parameters of super-commands.
- `choices` — Iterable of allowed values, or a callable (for dynamic choices). In interactive mode, values are validated against the list after type conversion. In CLI mode, argparse enforces choices at parse time (callables are excluded from argparse validation).
- `nargs` — Number of values. `1` means a single value. `-1` means consume all remaining positional tokens into a list (maps to argparse `"+"` with joining for string types).

The decorator writes into `fn.__arguments_decorator_specs` (a dict from parameter name to `_ArgDecoratorSpec`). It also writes into `fn.__annotations__` so the type is visible to `inspect.getfullargspec`.

---

## `FunctionInspection` and `inspect_object`

`inspect_object(obj)` is the central introspection function. It is called by `AutoCommand.__init__` and by `register_command` in the argparse module.

```python
FunctionInspection = namedtuple("FunctionInspection", "arguments command subcommands")
```

**`command`** — A `Command` named tuple `(name, help, aliases, exclusive_arguments)` built from `obj.__command`. `None` if the object has no `@command` decorator.

**`arguments`** — `OrderedDict[str, Argument]` keyed by the display name. Each `Argument` is:

```python
Argument = namedtuple(
    "Argument",
    "arg description type "
    "default_value_set default_value "
    "name extra_names positional choices nargs",
)
```

- `arg` — The Python parameter name (used when calling the function).
- `name` — The display/flag name (used in parsing and argparse registration).
- `type` — The resolved Python type (from annotation or `@argument type=`).
- `default_value_set` / `default_value` — Whether the parameter has a default and its value.
- `extra_names` — List of alias names from `@argument aliases=`.
- `positional`, `choices`, `nargs` — As specified in `@argument`.

**`subcommands`** — For classes only: list of `(attr_name, FunctionInspection)` pairs. Built by iterating `dir(obj)`, skipping private members and non-callables, and recursively calling `inspect_object` on each method that carries `@command`.

### Name transformation

`transform_name(name)` converts Python-style names to display names:
- Replaces runs of underscores with single dashes.
- Strips leading and trailing dashes.
- Example: `_foo_bar_` → `foo-bar`, `__verbose__` → `verbose`.

`transform_class_name(name)` also inserts dashes at CamelCase boundaries:
- Example: `ShowInterface` → `show-interface`.

---

## Type Inspection

`nubia/internal/typing/inspect.py`

These predicates test Python `typing` generics and are used throughout the builder and argparse modules.

| Function | Returns `True` when |
|---|---|
| `is_optional_type(tp)` | `tp` is `Optional[X]` (i.e. `Union[X, None]`). From `typing_inspect`. |
| `is_iterable_type(tp)` | `tp` is `Iterable` or a generic alias of `collections.abc.Iterable` (includes `List[X]`). On Python < 3.7, checks `issubclass(tp, list)`. |
| `is_mapping_type(tp)` | `tp` is `Mapping` or a generic alias of `collections.abc.Mapping` (includes `Dict[K, V]`). |
| `is_tuple_type(tp)` | From `typing_inspect`. True for `Tuple[...]`. |
| `is_list_type(tp)` | True specifically for `List[X]` or `list` origin. |
| `is_typevar(tp)` | From `typing_inspect`. True for `TypeVar` instances. |
| `is_none_type(tp)` | True for `type(None)`. |
| `get_first_type_argument(tp)` | Returns `tp.__args__[0]` (e.g. `int` from `List[int]`). |

### Python 3.7+ compatibility

The module uses the `NEW_TYPING` flag from `typing_inspect` to select between `_BaseGenericAlias` (Python 3.9+) and `_GenericAlias` (Python 3.7–3.8) as the base class for generic alias checks. This is necessary because `typing.List` and `typing.Dict` became `_SpecialGenericAlias` in 3.9, breaking naive `isinstance` checks.

---

## Type Building and Conversion

`nubia/internal/typing/builder.py`

### `build_value(string, tp=None, python_syntax=False)`

Entry point for converting a raw string token to a typed Python value. Two parsing strategies:

- **`python_syntax=False`** (interactive mode default) — calls `_build_simple_value(string, tp)`, which uses delimiter-based splitting without `eval`.
- **`python_syntax=True`** — calls `ast.literal_eval(string)` for safe evaluation of Python literals.

After parsing, `apply_typing(value, tp)` is called to enforce the target type.

### `apply_typing(value, tp)`

```python
def apply_typing(value, tp):
    return get_typing_function(tp)(value)
```

Dispatches to the appropriate converter based on the type. The converter is always a callable that takes one argument.

### `get_typing_function(tp)`

Selects and returns the conversion callable for a given type:

| Type | Converter |
|---|---|
| `str` or subclass | `str` |
| `typing.Any` | identity (no-op) |
| Unconstrained `TypeVar` | identity |
| Mapping type | `_apply_dict_type` |
| Tuple type | `_apply_tuple_type` |
| Iterable type | `_apply_list_type` |
| Optional type | `_apply_optional_type` |
| Any other callable | the type itself (called as a constructor) |

When the type has `__args__` (i.e. is a generic like `List[int]`), `get_typing_function` is applied recursively to each type argument, and the results are partially applied to the converter via `_partial_builder`.

### Converters

**`_apply_list_type(value, value_type=None)`** — Wraps a non-list value in a list, then maps `value_type` over each element. For `List[int]` and input `[" 1", "2"]`, produces `[1, 2]`.

**`_apply_dict_type(value, key_type=None, value_type=None)`** — Requires `value` to already be a dict (from `_build_simple_value`). Applies `key_type` and `value_type` to each entry. For `Dict[str, int]` and input `{"a": "1"}`, produces `{"a": 1}`.

**`_apply_tuple_type(value, *types)`** — Zips `types` with `value` elements and applies each type converter in order. Length must match.

**`_apply_optional_type(value, left_type=None, _right_type=None)`** — Returns `None` for `None` values, otherwise delegates to `left_type`. The `_right_type` (always `NoneType`) is ignored.

### `_build_simple_value` (interactive mode parsing)

Converts a raw string to a pre-typed structure before `apply_typing` runs:

| Target type | Splitting rule |
|---|---|
| `str` or no type | returned as-is |
| Mapping | split on `;` for entries, then on `:` or `=` for key/value |
| Tuple | split on `,` |
| Iterable | split on `,` |
| Anything else | returned as-is (type constructor handles it) |

For a `Mapping` where the value type is itself iterable, the value side is further split on `,`.

---

## ArgParse Integration

`nubia/internal/typing/argparse.py`

### `register_command(argparse_parser, inspection)`

Registers a command's subparser and arguments with argparse.

1. Resolves or creates the subparser action on `argparse_parser` via `_resolve_subparsers`.
2. Calls `subparsers.add_parser(name, aliases=aliases, help=help)` to create the command's subparser.
3. For each `Argument` in `inspection.arguments`, calls `_argument_to_argparse_input(arg)` to produce `(args, kwargs)` for `subparser.add_argument`.
4. If the argument belongs to an `exclusive_arguments` group, adds it to a `mutually_exclusive_group` instead.
5. If the command has sub-commands (`len(inspection.subcommands) > 0`), recursively calls `register_command` for each sub-command's inspection using a nested subparser action with `dest="_subcmd"`, `required=True`.

### `_argument_to_argparse_input(arg)`

Maps an `Argument` to the `(args_list, kwargs_dict)` pair passed to `add_argument`.

**Flag naming:** Positional arguments use `[arg.name]` as `args`. Optional arguments prefix with `--` for names longer than one character, `-` for single characters.

**Type mapping:**

| `arg.type` | argparse `type=` | argparse action |
|---|---|---|
| `int`, `float`, `str` | the type itself | default |
| `bool` or default `False` | — | `"store_true"` |
| default `True` | — | `"store_false"` |
| Mapping type | `_parse_dict(argument_type)` | default |
| Iterable/List type | `get_first_type_argument(tp)` | `nargs="+"` |
| `Optional[X]` | unwrapped inner type | same as inner type |
| Anything else | the type itself | default |

For `nargs=-1` (unlimited positionals), overrides `nargs` to `"+"`. For string types with `nargs=-1`, the argparse `type=` becomes a join function that merges multiple string tokens into one space-separated string.

**Choices:** If `arg.choices` is set and not callable, it is passed as `choices=` and the metavar is set to `{val1,val2,...}`. Callable choices are stripped before passing to argparse (validated separately in interactive mode).

### `get_arguments_for_command(function, parsed_args)`

Converts an `argparse.Namespace` back to the kwargs dict suitable for calling the function directly.

1. Calls `inspect_object(function)` to get the `FunctionInspection`.
2. Builds a reverse map from display names and aliases to Python parameter names.
3. Filters `parsed_args._get_kwargs()` to only the parameters the function actually accepts.

### `get_arguments_for_inspection(inspection, kwargs)`

Same as above but takes an already-built `FunctionInspection` and a plain dict. Used in `AutoCommand._create_subcommand_obj` to split class-level kwargs from sub-command kwargs.

### `create_subparser_class(opts_parser)`

Returns a dynamically created `SubParser` class that copies all optional arguments and mutually exclusive groups from the main parser into each sub-command parser. This allows global flags (e.g. `--verbose`) to appear after the subcommand name on the CLI.

---

## Error Handling

### `CommandParseError`

Raised by `nubia.internal.parser` when the interactive input cannot be tokenized. `AutoCommand.run_interactive` catches this and prints a caret-style error message pointing to the column where parsing failed.

### `ArgsValidationError`

Defined in `nubia/internal/exceptions.py`. Available for use by custom `Command` implementations that want to signal argument validation failures in a structured way. Not currently raised by `AutoCommand` directly (it uses integer return codes instead).

### `CommandError` / `UnknownCommand`

`CommandError` is the base class for command-level errors. `UnknownCommand` is raised by `HelpCommand` when `help <name>` is called with an unrecognized command name.

### Return codes from `run_interactive`

Type-related failures surface as integer return codes rather than exceptions:

| Code | Trigger |
|---|---|
| 4 | `apply_typing` raises `ValueError` (type conversion failed) |
| 4 | A value is not in the `choices` set |
| 3 | A required argument was not supplied |
| 2 | Unknown argument key, duplicate key, wrong positional count |
| 1 | Exception raised inside the user function |

The calling REPL loop receives the return code and may display it or use it to set the process exit status.
