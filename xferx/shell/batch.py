# Copyright (C) 2014 Andrea Bonomi <andrea.bonomi@gmail.com>

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import typing as t

from ..commons import splitdrive
from .cmds import cmds
from .commons import CommandError, ShellContext

__all__ = ["BatchContext"]


class BatchContext(ShellContext):

    lines: t.List[str]
    labels: t.Dict[str, int]
    current_line: int = 0
    next_line: int = 0
    on_error: str = "EXIT"

    def __init__(self, context: "ShellContext", fullname: str) -> None:
        super().__init__(context.shell)
        # Read the file
        self.lines = context.volumes.read_text(fullname=fullname, cmd="BATCH").split("\n")
        # Find labels
        self.labels = {}
        for i, raw_line in enumerate(self.lines):
            line = raw_line.strip()
            if line.startswith(":"):
                label_name = line[1:].strip().lower()
                self.labels[label_name] = i

    def execute(self) -> None:
        self.current_line = 0
        self.next_line = 0
        while self.next_line < len(self.lines):
            self.current_line = self.next_line
            raw_line = self.lines[self.current_line]
            self.next_line = self.current_line + 1
            line = raw_line.strip()
            if line.startswith("!"):
                continue
            try:
                self.shell.onecmd(line, batch=True, context=self)
            except Exception:
                self.shell.onecmd(self.on_error, batch=True, context=self)


@cmds.register("CONTINUE")
def continue_(context: "ShellContext", args: t.List[str]) -> None:
    # fmt: off
    """
CONTINUE        Continue the script execution

  SYNTAX
        CONTINUE

  SEMANTICS
    Resumes execution of a batch file.
    """
    # fmt: on
    if not isinstance(context, BatchContext):
        raise CommandError("?CONTINUE-F-Not in batch mode")


@cmds.register("GOTO")
def goto(context: "ShellContext", args: t.List[str]) -> None:
    # fmt: off
    """
GOTO            Transfers control to a labeled statement

  SYNTAX
        GOTO label

  SEMANTICS
    Transfers control to a labeled statement in a batch file.
    """
    # fmt: on
    if not isinstance(context, BatchContext):
        raise CommandError("?GOTO-F-Not in batch mode")
    try:
        label = args[0]
        context.next_line = context.labels[label.strip().lower()]
    except Exception:
        raise CommandError("?GOTO-F-Label not found")


@cmds.register("ON")
def on(context: "ShellContext", args: t.List[str]) -> None:
    # fmt: off
    """
ON              Change the course of action when a command encounters an error

  SYNTAX
        ON severity-level THEN command

  SEMANTICS
        With the ON command, you can establish a course of action
        for the command interpreter to take when a command encounters an error.

  EXAMPLES
        ON ERROR EXIT
        ON ERROR CONTINUE
    """
    # fmt: on
    if not isinstance(context, BatchContext):
        raise CommandError("?ON-F-Not in batch mode")
    if len(args) < 3:
        raise CommandError("?ON-F-Too few arguments")
    if args[0].upper() != "ERROR":
        raise CommandError("?ON-F-Invalid severity level")
    if args[1].upper() != "THEN":
        raise CommandError("?ON-F-THEN expected")
    context.on_error = " ".join(args[2:])
