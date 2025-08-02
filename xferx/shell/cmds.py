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

import importlib.resources
import os
import shlex
import sys
import typing as t

from ..commons import ASCII, splitdrive
from ..volumes import DEFAULT_VOLUME, FILESYSTEMS
from .commons import (
    CommandError,
    Commands,
    ask,
    copy_file,
    extract_options,
    get_int_option,
)

if t.TYPE_CHECKING:
    from ..shell import Shell

__all__ = ["cmds"]


cmds = Commands()


@cmds.register("DIR_ECTORY", aliases=["LS"])
def directory(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
DIR             Lists file directories

  SYNTAX
        DIR [/options] [[volume:][filespec]]

  SEMANTICS
        This command generates a listing of the directory you specify.

  OPTIONS
   BRIEF
        Lists only file names and file types
   FULL
        Lists the entire directory, including unused areas
   UIC
        Lists all UIC on a device (DOS-11, RSTS/E)

  EXAMPLES
        DIR A:*.SAV
        DIR SY:

    """
    # fmt: on
    args, options = extract_options(args, "/brief", "/uic", "/full")
    if len(args) > 1:
        raise CommandError("?DIR-F-Too many arguments")
    if args:
        volume_id, pattern = splitdrive(args[0])
    else:
        volume_id = DEFAULT_VOLUME
        pattern = None
    fs = shell.volumes.get(volume_id, cmd="DIR")
    fs.dir(volume_id, pattern, options)  # type: ignore


@cmds.register("TY_PE")
def type(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
TYPE            Outputs files to the terminal

  SYNTAX
        TYPE [volume:]filespec

  EXAMPLES
        TYPE A.TXT

    """
    # fmt: on
    if not args:
        line = ask("File? ")
        args = shlex.split(line)
    if len(args) > 1:
        raise CommandError("?TYPE-F-Too many arguments")
    volume_id, pattern = splitdrive(args[0])
    fs = shell.volumes.get(volume_id, cmd="TYPE")
    match = False
    for entry in fs.filter_entries_list(pattern):
        match = True
        content = entry.read_bytes(file_mode=ASCII)
        if content is not None:
            os.write(sys.stdout.fileno(), content)
            sys.stdout.write("\n")
    if not match:
        raise CommandError("?TYPE-F-No files")


@cmds.register("COP_Y")
def copy(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
COPY            Copies files

  SYNTAX
        COPY [/options] [input-volume:]input-filespec [output-volume:][output-filespec]

  OPTIONS
   ASCII                Copy as ASCII text
   TYPE:type
        Specifies that the output file type, if supported by the target filesystem
        See the SHOW TYPES command for a list of filesystems.

  EXAMPLES
        COPY *.TXT DK:
        COPY /ASCII /TYPE:CONTIGUOUS LICENSE DK:

    """
    # fmt: on
    args, options = extract_options(args, "/ascii", "/type")
    if len(args) > 2:
        raise CommandError("?COPY-F-Too many arguments")
    file_mode = ASCII if options.get("ascii") else None
    cfrom = len(args) > 0 and args[0]
    to = len(args) > 1 and args[1]
    if not cfrom:
        cfrom = ask("From? ")
    from_volume_id, cfrom = splitdrive(cfrom)
    from_fs = shell.volumes.get(from_volume_id, cmd="COPY")
    if not to:
        to = ask("To? ")
    to_volume_id, to = splitdrive(to)
    to_fs = shell.volumes.get(to_volume_id, cmd="COPY")
    from_len = len(list(from_fs.filter_entries_list(cfrom)))
    from_list = from_fs.filter_entries_list(cfrom)
    file_type = options["type"].upper() if isinstance(options.get("type"), str) else None  # type: ignore
    if from_len == 0:  # No files
        raise CommandError("?COPY-F-No files")
    elif from_len == 1:  # One file to be copied
        source = list(from_list)[0]
        if not to:
            to_pwd = shell.volumes.get(to_volume_id).get_pwd()
            to_path = os.path.join(to_pwd, source.basename)
        elif to and to_fs.isdir(to):
            to_path = os.path.join(to, source.basename)
        else:
            to_path = to
        from_entry = from_fs.get_file_entry(source.fullname)
        if not from_entry:
            raise CommandError(f"?COPY-F-Error copying {source.fullname}")
        sys.stdout.write("%s:%s -> %s:%s\n" % (from_volume_id, source.fullname, to_volume_id, to_path))
        copy_file(from_fs, from_entry, to_fs, to_path, file_type, file_mode, shell.verbose, cmd="COPY")
    else:
        if not to:
            to = shell.volumes.get(to_volume_id).get_pwd()
        elif not to_fs.isdir(to):
            raise CommandError("?COPY-F-Target must be a volume or a directory")
        for from_entry in from_fs.filter_entries_list(cfrom):
            if to:
                to_path = os.path.join(to, from_entry.basename)
            else:
                to_path = from_entry.basename
            sys.stdout.write("%s:%s -> %s:%s\n" % (from_volume_id, from_entry.fullname, to_volume_id, to_path))
            copy_file(from_fs, from_entry, to_fs, to_path, file_type, file_mode, shell.verbose, cmd="COPY")


@cmds.register("DEL_ETE")
def delete(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
DELETE          Removes files from a volume

  SYNTAX
        DELETE [volume:]filespec

  SEMANTICS
        This command deletes the files you specify from the volume.

  EXAMPLES
        DELETE *.OBJ

    """
    # fmt: on
    if not args:
        line = ask("Files? ")
        args = shlex.split(line)
    volume_id, pattern = splitdrive(args[0])
    fs = shell.volumes.get(volume_id, cmd="DEL")
    match = False
    for x in fs.filter_entries_list(pattern, expand=False):  # don't expand directories
        match = True
        if not x.delete():
            sys.stdout.write("?DEL-F-Error deleting %s\n" % x.fullname)
    if not match:
        raise CommandError("?DEL-F-No files")


@cmds.register("E_XAMINE")
def examine(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
EXAMINE         Examines disk structure

  SYNTAX
        EXAMINE volume:

   FULL
        Lists the entire directory, including unused areas

    """
    # fmt: on
    args, options = extract_options(args, "/free", "/bitmap", "/diskid", "/full")
    if not args:
        args = ask("From? ").split()
    for arg in args:
        volume_id, fullname = splitdrive(arg)
        fs = shell.volumes.get(volume_id)
        fs.examine(fullname, options)


@cmds.register("DU_MP")
def dump(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
DUMP            Prints formatted data dumps of files or devices

  SYNTAX
        DUMP [/options] filespec

  SEMANTICS
        Filespec represents the device or file to be dumped.

  OPTIONS
   START:block
        Specifies the first block to be dumped
   END:block
        Specifies the last block to be dumped

  EXAMPLES
        DUMP A.OBJ
        DUMP /START:6 /END:6 DL0:

    """
    # fmt: on
    args, options = extract_options(args, "/start", "/end")
    start = get_int_option(options, "start")
    end = get_int_option(options, "end")
    if not args:
        args = ask("From? ").split()
    for arg in args:
        try:
            volume_id, fullname = splitdrive(arg)
            fs = shell.volumes.get(volume_id)
            fs.dump(fullname, start=start, end=end)
        except FileNotFoundError:
            raise CommandError("?DUMP-F-File not found")


@cmds.register("CR_EATE")
def create(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
CREATE          Creates files or directories

  SYNTAX
        CREATE [/options] [volume:]filespec

  SEMANTICS
        This command creates a file or directory on the volume you specify.
        The default option is to create a file.

  OPTIONS
   FILE
        Creates a file with a specific name and size
   DIRECTORY
        Creates a directory
   ALLOCATE:size
        Specifies the number of blocks to allocate to the created file
   TYPE:type
        Specifies the file type
        See the SHOW TYPES command for a list of filesystems.

  EXAMPLES
        CREATE NEW.DSK /ALLOCATE:200

    """
    # fmt: on
    args, options = extract_options(args, "/file", "/dir", "/directory", "/uic", "/allocate", "/type")
    if len(args) > 1:
        raise CommandError("?CREATE-F-Too many arguments")
    if "file" in options:
        kind = "file"
    if "directory" in options or "dir" in options:
        kind = "directory"
    else:
        kind = "file"
    path = len(args) > 0 and args[0]
    if not path:
        path = ask("File? ")
    volume_id, fullname = splitdrive(path)
    fs = shell.volumes.get(volume_id, cmd="CREATE")
    if kind == "directory":
        # Create a directory
        fs.create_directory(fullname, options)
    else:
        # Create a file
        allocate = options.get("allocate")
        if not allocate:
            allocate = ask("Size? ")
        try:
            number_of_blocks = int(allocate)
            if number_of_blocks < 0:
                raise ValueError
        except:
            raise CommandError("?CREATE-F-Invalid value specified with option")
        fs.create_file(
            fullname,
            number_of_blocks=number_of_blocks,
            file_type=options.get("type") if isinstance(options.get("type"), str) else None,  # type: ignore
        )


@cmds.register("MO_UNT")
def mount(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
MOUNT           Assigns a logical disk unit to a file

  SYNTAX
        MOUNT [/options] volume: [volume:]filespec

  SEMANTICS
        Associates a logical disk unit with a file.
        See the SHOW FILESYSTEMS command for a list of filesystems
        that can be mounted.

  EXAMPLES
        MOUNT AB: SY:rt11v503.dsk
        MOUNT /DOS11 AB: SY:dos.dsk
        MOUNT /UNIX7 AB: SY:unix7.dsk
        MOUNT /DMS /DEV:DECTAPE AB: SY:dms.tu56

  OPTIONS
   DEV:device type
        Specifies the device type, if supported by the target filesystem.

    """
    # fmt: on
    fs_args = [f"/{x}" for x in FILESYSTEMS.keys()]
    args, options = extract_options(args, "/dev", *fs_args)
    try:
        device_type: t.Optional[str] = options["dev"].lower()  # type: ignore
    except Exception:
        device_type = None
    if len(args) > 2:
        raise CommandError("?MOUNT-F-Too many arguments")
    logical = len(args) > 0 and args[0]
    path = len(args) > 1 and args[1]
    if not logical:
        logical = ask("Volume? ")
    if not path:
        path = ask("File? ")
    fstype = None
    for filesystem in FILESYSTEMS.keys():
        if options.get(filesystem):
            fstype = filesystem
            break
    shell.volumes.mount(path, logical, fstype=fstype, verbose=shell.verbose, device_type=device_type)


@cmds.register("DIS_MOUNT")
def dismount(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
DISMOUNT        Disassociates a logical disk assignment from a file

  SYNTAX
        DISMOUNT logical_name

  SEMANTICS
        Removes the association of a logical disk unit with its currently
        assigned file, thereby freeing it to be assigned to another file.

  EXAMPLES
        DISMOUNT AB:

    """
    # fmt: on
    if len(args) > 1:
        raise CommandError("?DISMOUNT-F-Too many arguments")
    if args:
        logical = args[0]
    else:
        logical = ask("Volume? ")
    shell.volumes.dismount(logical)


@cmds.register("AS_SIGN")
def assign(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
ASSIGN          Associates a logical device name with a device

  SYNTAX
        ASSIGN device-name logical-device-name

  SEMANTICS
        Associates a logical device name with a device.
        Logical-device-name is one to three alphanumeric characters long.

  EXAMPLES
        ASSIGN DL0: INP:

    """
    # fmt: on
    args, options = extract_options(args)
    if len(args) > 2:
        raise CommandError("?ASSIGN-F-Too many arguments")
    volume_id = len(args) > 0 and args[0]
    logical = len(args) > 1 and args[1]
    if not volume_id:
        volume_id = ask("Device name? ")
    if not logical:
        logical = ask("Logical name? ")
    shell.volumes.assign(volume_id, logical, verbose=shell.verbose)


@cmds.register("DEA_SSIGN")
def deassign(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
DEASSIGN        Removes logical device name assignments

  SYNTAX
        DEASSIGN logical-device-name

  SEMANTICS
        The DEASSIGN command disassociates a logical name.

  EXAMPLES
        DEASSIGN INP:

    """
    # fmt: on
    if len(args) > 1:
        raise CommandError("?DEASSIGN-F-Too many arguments")
    if args:
        logical = args[0]
    else:
        logical = ask("Volume? ")
    shell.volumes.deassign(logical, cmd="DEASSIGN")


@cmds.register("INI_TIALIZE")
def initialize(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
INITIALIZE      Writes an empty device directory on the specified volume

  SYNTAX
        INITIALIZE [/options] [volume:][filespec]]

  SEMANTICS
        Initializes the specified filesystem on the volume.
        Any data on the volume is lost.
        See the SHOW FILESYSTEMS command for a list of filesystems.

  EXAMPLES
        INIT /DOS11 /DEV:dectape test.tap

  OPTIONS
   NAME:name
        Specifies the volume name
   DEV:device type
        Specifies the device type, if supported by the target filesystem.

    """
    # fmt: on
    fs_args = [f"/{x}" for x in FILESYSTEMS.keys()]
    args, options = extract_options(args, "/name", "/dev", *fs_args)
    if len(args) > 1:
        raise CommandError("?INITIALIZE-F-Too many arguments")
    target = len(args) > 0 and args[0]
    if not target:
        target = ask("Volume? ")
    if target.endswith(":"):
        try:
            options["device_type"] = options["dev"].lower()  # type: ignore
        except Exception:
            pass
        fs = shell.volumes.get(target)
        fs.initialize(fs.dev, **options)
    else:
        filesystem_cls = None
        for k, v in FILESYSTEMS.items():
            if options.get(k):
                filesystem_cls = v
                break
        if filesystem_cls is None:
            raise CommandError("?INITIALIZE-F-Filesystem not specified")
        parent_volume_id, target_path = splitdrive(target)
        parent_fs = shell.volumes.get(parent_volume_id)
        target_file = parent_fs.open_file(target_path)
        try:
            device_type = options["dev"].lower()  # type: ignore
        except Exception:
            device_type = shell.volumes.guess_device_type(target_path)
        if device_type:
            options["device_type"] = device_type
        fs = filesystem_cls.initialize(target_file, **options)
        fs.close()


@cmds.register("CD")
def cd(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
CD              Changes or displays the current working drive and directory

  SYNTAX
        CD [[volume:][filespec]]

    """
    # fmt: on
    if len(args) > 1:
        raise CommandError("?CD-F-Too many arguments")
    elif len(args) == 0:
        sys.stdout.write("%s\n" % shell.volumes.get_pwd())
    elif not shell.volumes.chdir(args[0]):
        raise CommandError("?CD-F-Directory not found")


@cmds.register("@", aliases=["BATCH"])
def batch(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
@               Executes a command file

  SYNTAX
        @[volume:]filespec

  SEMANTICS
        You can group a collection of commands that you want to execute
        sequentially into a command file.
        This command executes the command file.

  EXAMPLES
        @MAKE.COM

    """
    # fmt: on
    if not args:
        return
    try:
        volume_id, filespec = splitdrive(args[0])
        fs = shell.volumes.get(volume_id, cmd="BATCH")
        for line in fs.read_text(filespec).split("\n"):
            if line.startswith("!"):
                continue
            shell.onecmd(line.strip(), catch_exceptions=False, batch=True)
    except SystemExit:
        pass
    except FileNotFoundError:
        raise CommandError("?KMON-F-File not found")


@cmds.register("PWD")
def pwd(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
PWD             Displays the current working drive and directory

  SYNTAX
        PWD

    """
    sys.stdout.write("%s\n" % shell.volumes.get_pwd())


@cmds.register("SH_OW")
def show(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
SHOW            Displays software status

  SYNTAX
        SHOW [options] [volume:]

  SEMANTICS
	    SHOW displays the device assignments; other information
	    is displayed by specifying one or more option names.

  OPTIONS
   FILESYSTEMS
        Show the supported filesystems
   TYPES
        Show the file types of a volume
   VERSION
        Show the version of XFERX
   VOLUMES
        Show the device assignments

  EXAMPLES
        SHOW
        SHOW FILESYSTEMS
        SHOW TYPES DL0:

    """
    # fmt: on
    func = cmds.get(f"SHOW {args[0]}" if args else "SHOW VOLUMES")
    if func is None:
        raise CommandError("?SHOW-F-Illegal command")
    func(shell, args)


@cmds.register("SHOW T_YPES")
def show_type(shell: "Shell", args: t.List[str]) -> None:
    """
    SHOW TYPES        Show the file types of a volume
    """
    # fmt: on
    if len(args) == 1:
        volume_id = ask("Volume? ")
    else:
        volume_id = args[1]
    fs = shell.volumes.get(volume_id)
    sys.stdout.write("File Types\n")
    sys.stdout.write("----------\n")
    for item in fs.get_types():
        sys.stdout.write(f"{item}\n")


@cmds.register("SHOW F_ILESYSTEMS", aliases=["SHOW FS"])
def show_filesystems(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
SHOW FILESYSTEMS  Show the supported filesystems
    """
    # fmt: on
    sys.stdout.write("Filesystems\n")
    sys.stdout.write("-----------\n")
    for k, v in sorted(FILESYSTEMS.items()):  # type: ignore
        sys.stdout.write(f"{k.upper():<10} {v.fs_description}\n")


@cmds.register("SHOW VE_RSION")
def show_version(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
SHOW VERSION      Show the version of XFERX
    """
    # fmt: on
    with importlib.resources.files("xferx").joinpath("VERSION").open("r", encoding="utf-8") as f:
        version = f.read().strip()
    sys.stdout.write(f"XFERX {version}\n")


@cmds.register("SHOW VO_LUMES")
def show_volumes(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
SHOW VOLUMES      Show the device assignments
    """
    # fmt: on
    sys.stdout.write("Volumes\n")
    sys.stdout.write("-------\n")
    for k, v in shell.volumes.volumes.items():
        label = f"{k}:"
        sys.stdout.write(f"{label:<6} {v}\n")
    for k, v in shell.volumes.logical.items():  # type: ignore
        label = f"{k}:"
        sys.stdout.write(f"{label:<4} = {v}:\n")


@cmds.register("EXIT", aliases=["QUIT"])
def exit(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
EXIT            Exit the shell

  SYNTAX
        EXIT
    """
    # fmt: on
    raise SystemExit


@cmds.register("H_ELP")
def help(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
HELP            Displays commands help

  SYNTAX
        HELP [topic]

    """
    # fmt: on
    if args and args[0] != "*":
        arg = args[0]
        func = cmds.get(arg)
        if func is None:
            raise CommandError(f"?HELP-F-Help not available for {arg}")
        sys.stdout.write(f"{func.__doc__}\n")
    else:
        for name, command in sorted(cmds.commands.items()):
            if not " " in name and command.__doc__ is not None:
                sys.stdout.write(command.__doc__.split("\n")[1])
                sys.stdout.write("\n")


@cmds.register("SHELL")
def shell(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
SHELL           Executes a system shell command

  SYNTAX
        SHELL command

    """
    # fmt: on
    os.system(shlex.join(args))


@cmds.register("ECHO")
def echo(shell: "Shell", args: t.List[str]) -> None:
    # fmt: off
    """
ECHO            Write arguments to the terminal

  SYNTAX
        ECHO [arg ...]

  EXAMPLES
        ECHO Hello World

    """
    # fmt: on
    line = " ".join(args).strip()
    sys.stdout.write(f"{line}\n")
