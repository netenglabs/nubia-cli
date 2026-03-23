# Data Flows

This document traces the four principal execution paths through Nubia.

---

## 1. Command Loading Flow (startup)

Triggered by `Nubia.__init__()` followed by `Nubia.run()` / `Nubia._pre_run()`.

**nubia/internal/nubia.py**

```
Nubia.__init__()
  context._ctx = plugin.create_context()       # install global context singleton
  ctx.set_binary_name(name)
```

```
Nubia._pre_run(cli_args)                        # nubia.py:230
  1.  opts_parser = plugin.get_opts_parser()
  2.  SubParser  = create_subparser_class(opts_parser)   # typing/argparse.py:36
        # produces a subclass that copies global flags into every subparser

  3.  cmd_parser = opts_parser.add_subparsers(dest="_cmd", ...)

  4.  registry = CommandsRegistry(cmd_parser, listeners)  # registry.py:25
        # initialises:
        #   _cmd_instance_map  = {}          (name → Command)
        #   _completer.words   = []          (prompt_toolkit WordCompleter)
        #   _listeners         = []

  5.  ctx.set_registry(registry)
      registry.register_priority_listener(ctx)   # Context is listener #0

  6.  for cmd in builtin_cmds:
          registry.register_command(cmd())        # Connect, Exit, Verbose, Help

  7.  for cmd in plugin.get_commands():
          registry.register_command(cmd, override=True)

  8.  for pkg in command_pkgs:
          for fn in cmdloader.load_commands(pkg):  # cmdloader.py:32
              registry.register_command(AutoCommand(fn, options), override=True)
```

**cmdloader.load_commands(pkg)** — `nubia/internal/cmdloader.py:32`

```
  _walk_package(name, path)
    pkgutil.walk_packages(path)           # recurse all sub-modules
    for each module:
        _walk_module(module)
          for attr in dir(module):
              if hasattr(member, "__command"):   # set by @command decorator
                  yield member
```

**registry.register_command(cmd_instance)** — `nubia/internal/registry.py:37`

```
  cmd_instance.set_command_registry(self)
  cmd_keys = cmd_instance.get_command_names()   # [name] + aliases
  await cmd_instance.add_arguments(self._parser)
      # For AutoCommand: calls typing/argparse.register_command()
      #   which calls subparsers.add_parser(name, aliases=..., help=...)
      #   then adds each argument via _argument_to_argparse_input()

  for cmd in cmd_keys:
      _cmd_instance_map[cmd.lower()] = cmd_instance
      _completer.words.append(cmd)               # completion word list updated
      _completer.meta_dict[cmd] = short_help

  for alias in cmd_instance.get_cli_aliases():
      _cmd_instance_map[alias.lower()] = cmd_instance   # alias resolution
```

**AutoCommand.__init__()** — `nubia/internal/cmdbase.py:148`

```
  _obj_metadata = inspect_object(fn)   # typing/__init__.py:234
      # reads __command and __arguments_decorator_specs set by @command / @argument
      # returns FunctionInspection(arguments, command, subcommands)
  _is_super_command = len(metadata.subcommands) > 0
  if super_command:
      build _commands_completer with sub-command names
```

At the end of `_pre_run`, argparse is fully populated and `_cmd_instance_map` maps every command name (and alias) to its `Command` instance.

---

## 2. Interactive Mode Flow (user types a command)

Entered when no CLI subcommand is given; `args._cmd == "connect"` routes to `start_interactive`.

**nubia/internal/nubia.py:162**

```
start_interactive(args)
  io_loop = IOLoop(ctx, plugin, usage_logger, options)   # interactive.py:39
  await ctx.on_interactive(args)       # lifecycle hook
  if sys.stdin.isatty():
      await io_loop.run()
  else:
      # stdin mode — see Flow 4
```

**IOLoop.run()** — `nubia/internal/interactive.py:144`

```
  prompt = _build_cli()
      # PromptSession with:
      #   history  = FileHistory(~/.{name}_history) or InMemoryHistory
      #   completer = ShellCompleter(registry)
      #   lexer    = PygmentsLexer(NubiaLexer)

  while True:
      text = await prompt.prompt_async(...)   # blocks for keypress
      await parse_and_evaluate(text)
```

**IOLoop.parse_and_evaluate(input)** — `interactive.py:86`

```
  1.  command_parts = split_command(input)
          # split_command: input.lstrip().split(" ", 1)
          # => [cmd_name, rest_of_line]

  2.  cmd  = command_parts[0]
      args = command_parts[1] if len > 1 else None
      await evaluate_command(cmd, args, input)
```

**IOLoop.evaluate_command(cmd, args, raw)** — `interactive.py:93`

```
  3.  if cmd in registry:                          # registry.__contains__
          cmd_instance = registry.find_command(cmd)    # dict lookup, lowercased
      else:
          suggestions = find_approx(cmd, registry.get_all_commands_map())
          # auto-correct if single suggestion and option enabled, else error

  4.  blacklist.is_blacklisted(cmd)

  5.  usagelogger.pre_exec()
      result = await cmd_instance.run_interactive(cmd, args, raw)
      usagelogger.post_exec(...)
      status_bar.set_last_command_status(result)
```

**AutoCommand.run_interactive(cmd, args, raw)** — `cmdbase.py:214`

```
  6.  parsed = parser.parse(args, expect_subcommand=self.super_command)
          # parser.py:111 — pyparsing grammar applied to the args string
          # returns ParseResults with:
          #   .positionals   list of bare values
          #   .kv            dict of key=value pairs
          #   .__subcommand__ name of sub-command (if super_command)

  7.  if super_command:
          subcommand = parsed["__subcommand__"]
          instance, remaining = _create_subcommand_obj(args_dict)
              # instantiates the class (fn) with its constructor args
          fn = getattr(instance, subcommand_method_name)
          args_metadata = sub_inspection.arguments
      else:
          fn = self._fn

  8.  positionals resolved against can_be_positional (args with positional=True)
      duplicate-key check
      extra-key check (unknown argument names → return 2)
      missing required-key check (→ return 3)

  9.  for key, value in args_dict.items():
          new_value = apply_typing(value, target_type)   # typing/builder.py
          # raises ValueError on bad conversion → return 4

  10. choices validation (static choices only)

  11. args_dict = {metadata[k].arg: v ...}   # remap to function param names
      ctx.cmd    = cmd
      ctx.raw_cmd = raw
      ret = await try_await(fn(**args_dict))

  return ret
```

Return value conventions: `None` → 0, `int` returned directly, exception → 1.

---

## 3. CLI Mode Flow (command on argv)

Triggered when `sys.argv` contains a recognised subcommand name.

**nubia/internal/nubia.py**

```
Nubia.run(cli_args)
  asyncio.run(run_async(cli_args))

run_async(cli_args)
  1.  args = await _pre_run(cli_args)     # sets up registry and argparse (Flow 1)

  2.  _parse_args(cli_args)               # nubia.py:182
          cli_args = cli_args[1:]          # strip binary name
          args, extra = opts_parser.parse_known_args(cli_args)
          # unrecognised args moved to end; full parse retried
          # result: args._cmd = subcommand name

  3.  if args._cmd != "connect":
          await run_cli(args)
```

**Nubia.run_cli(args)** — `nubia.py:212`

```
  4.  blacklist.is_blacklisted(args._cmd)

  5.  await ctx.on_cli(args._cmd, args)      # lifecycle hook

  6.  cmd_instance = registry.find_command(args._cmd)   # registry.py:108
          # _cmd_instance_map.get(cmd.lower())

  7.  ret = await cmd_instance.run_cli(args)
```

**AutoCommand.run_cli(args)** — `cmdbase.py:479`

```
  8.  kwargs = _kwargs_for_fn(self._fn, args)
          # typing/argparse.get_arguments_for_command(fn, parsed_args)
          #   maps argparse namespace keys back to function parameter names
          #   strips _cmd, _subcmd, and other framework keys

  9.  if _is_super_command:
          instance = self._fn(**kwargs)         # instantiate the class
          attrname = _find_subcommand_attr(args._subcmd)
          fn = getattr(instance, attrname)
          kwargs = _kwargs_for_fn(fn, args)
      else:
          fn = self._fn

  10. ret = await try_await(fn(**kwargs))
      return ret
```

**Exit code mapping** (in `run_async`):
- `int` → returned as-is
- `bool` → `int(not ret)` (True → 0, False → 1)
- `None` → 0
- anything else → 1

---

## 4. Stdin Mode Flow (piped input)

Activated when `start_interactive` is called but `sys.stdin.isatty()` is `False`.

**nubia/internal/nubia.py:162 / interactive.py**

```
start_interactive(args)
  io_loop = await _create_interactive_io_loop(args)
      # IOLoop constructed the same as interactive mode
      # ctx.on_interactive(args) called

  if not sys.stdin.isatty():
      commands = sys.stdin.readlines()       # read entire stdin at once
      for command in commands:
          print("> {}".format(command))       # echo command to stdout
          ret = await io_loop.parse_and_evaluate(command)
          if ret:                             # non-zero → abort on first failure
              return ret
      return 0
```

Each line is processed through the same `parse_and_evaluate → evaluate_command → run_interactive` chain as interactive mode (Flow 2). No readline/prompt_toolkit UI is constructed; `_build_cli()` is never called.

Error handling: the first command returning a non-zero exit code terminates the loop immediately and returns that code. Subsequent commands are not executed.
