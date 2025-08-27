import pytest

from xferx.commons import bytes_to_word, word_to_bytes
from xferx.pdp11.rad50 import asc2rad, rad2asc
from xferx.shell.commons import PartialMatching, extract_options
from xferx.shell.kmon import split_arguments


def test_bytes_to_word():
    # Test with valid input
    assert bytes_to_word(b"\x01\x00") == 1
    assert bytes_to_word(b"\xff\xff") == 65535
    assert bytes_to_word(b"\x01\xab\xcd", position=1) == 52651
    # Test with out of bounds position
    with pytest.raises(IndexError):
        bytes_to_word(b"\x01\x02", position=2)


def test_word_to_bytes():
    # Test with valid input
    assert word_to_bytes(1) == b"\x01\x00"
    assert word_to_bytes(65535) == b"\xff\xff"
    assert len(word_to_bytes(1234)) == 2
    for i in range(0, 1 << 16):
        assert bytes_to_word(word_to_bytes(i)) == i
    # Test with negative value
    with pytest.raises(ValueError):
        word_to_bytes(-1)
    # Test with value exceeding 16-bit range
    with pytest.raises(ValueError):
        word_to_bytes(2**16)


def test_rad2asc():
    # Test with valid input
    assert rad2asc(b"\x01\x00") == "A"
    assert rad2asc(b"\x06\x01") == "FV"
    assert rad2asc(b"\x00\x00") == ""
    # Test with different positions
    assert rad2asc(b"\x10\x37\x31\x43\x74", position=0) == "H2P"
    assert rad2asc(b"\x10\x37\x31\x43\x74", position=2) == "J0A"
    # Test with all zeros
    assert rad2asc(b"\x00\x00\x00") == ""


def test_asc2rad():
    # Test with valid input
    assert asc2rad("ABC") == b"\x93\x06"
    assert asc2rad("Z12") == b"x\xa7"
    assert asc2rad("") == b"\x00\x00"
    # Test with lowercase characters
    assert asc2rad("zia") == b"\xe9\xa3"
    assert asc2rad(":$%") == b"\x54\xfe"


def test_split_argument_basic():
    # Test parsing of basic unquoted arguments
    result = split_arguments("ls -la /home", platform='linux')
    expected = ["ls", "-la", "/home"]
    assert result == expected

    # Test parsing of empty string
    result = split_arguments("", platform='linux')
    expected = []
    assert result == expected

    # Test parsing of string with only whitespace
    result = split_arguments("   \t  ", platform='linux')
    expected = []
    assert result == expected

    # Test parsing of single argument
    result = split_arguments("hello", platform='linux')
    expected = ["hello"]
    assert result == expected

    # Test parsing with multiple spaces between arguments
    result = split_arguments("arg1    arg2     arg3", platform='linux')
    expected = ["arg1", "arg2", "arg3"]
    assert result == expected


def test_split_argument_posix():
    # Test basic quoteing scenarios
    for input_cmd, expected in [
        ('echo "hello world"', ["echo", "hello world"]),
        ("echo 'hello world'", ["echo", "hello world"]),
        ('echo "" \'\'', ["echo", "", ""]),
        ('echo "double" \'single\' unquoted', ["echo", "double", "single", "unquoted"]),
    ]:
        result = split_arguments(input_cmd, platform='linux')
        assert result == expected

    # Test escaped quotes within double quotes
    result = split_arguments(r'echo "Say \"hello\""', platform='linux')
    expected = ["echo", 'Say "hello"']
    assert result == expected

    # Test escaped backslashes within double quotes
    result = split_arguments(r'echo "path\\to\\file"', platform='linux')
    expected = ["echo", r"path\to\file"]
    assert result == expected

    # Test that single quotes preserve all characters literally
    result = split_arguments("echo 'no \"escaping\" in single quotes'", platform='linux')
    expected = ["echo", 'no "escaping" in single quotes']
    assert result == expected

    # Test escaped characters outside of quotes
    result = split_arguments(r"echo hello\ world", platform='linux')
    expected = ["echo", "hello world"]
    assert result == expected

    # Test concatenated quoted and unquoted parts
    result = split_arguments('echo "hello"world\'test\'', platform='linux')
    expected = ["echo", "helloworldtest"]
    assert result == expected

    # Test parsing a complex git command
    cmd = 'git commit -m "Fix bug in parser" --author="John Doe <john@example.com>"'
    result = split_arguments(cmd, platform='linux')
    expected = ["git", "commit", "-m", "Fix bug in parser", "--author=John Doe <john@example.com>"]
    assert result == expected

    # Test parsing a find command with escaped characters
    cmd = r"find . -name '*.py' -exec grep -l 'def test_' {} \;"
    result = split_arguments(cmd, platform='linux')
    expected = ["find", ".", "-name", "*.py", "-exec", "grep", "-l", "def test_", "{}", ";"]
    assert result == expected

    # Test parsing a Docker run command
    cmd = 'docker run -it --rm -v "/host/path:/container/path" ubuntu:latest bash'
    result = split_arguments(cmd, platform='linux')
    expected = ["docker", "run", "-it", "--rm", "-v", "/host/path:/container/path", "ubuntu:latest", "bash"]
    assert result == expected

    # Test parsing command with environment variable assignment
    cmd = 'ENV_VAR="some value" python script.py'
    result = split_arguments(cmd, platform='linux')
    expected = ["ENV_VAR=some value", "python", "script.py"]
    assert result == expected

    # Test deeply nested quoting scenarios
    cmd = r'echo "outer \"middle \\\"inner\\\" middle\" outer"'
    result = split_arguments(cmd, platform='linux')
    expected = ["echo", r'outer "middle \"inner\" middle" outer']
    assert result == expected

    # Test handling of Unicode characters
    cmd = 'echo "Hello 世界" café'
    result = split_arguments(cmd, platform='linux')
    expected = ["echo", "Hello 世界", "café"]
    assert result == expected


def test_partial_matching():
    x = PartialMatching()
    x.add("APP_LE")
    x.add("PE_AR")
    x.add("O_RANGE")
    x.add("D")
    x.add("DA_TE")

    # Test partial matching keys
    assert x.get("APP") == "APPLE"
    assert x.get("PE") == "PEAR"
    assert x.get("PEA") == "PEAR"
    assert x.get("O") == "ORANGE"
    assert x.get("OR") == "ORANGE"
    assert x.get("ORA") == "ORANGE"
    assert x.get("ORAN") == "ORANGE"
    assert x.get("D") == "D"
    assert x.get("DA") == "DATE"
    assert x.get("DAT") == "DATE"
    assert x.get("DATE") == "DATE"

    # Test non-partial matching keys
    assert x.get("XXX") is None
    assert x.get("XX") is None
    assert x.get("A") is None
    assert x.get("P") is None
    assert x.get("PE_X") is None
    assert x.get("O_") is None
    assert x.get("ORANGO") is None
    assert x.get("TD") is None
    assert x.get("") is None


def test_split_argument_windows():
    # Test simple double-quoted strings on Windows
    result = split_arguments('echo "hello world"', platform='win32')
    expected = ["echo", "hello world"]
    assert result == expected

    # Test escaped quotes in Windows style
    result = split_arguments(r'echo "Say \"hello\""', platform='win32')
    expected = ["echo", 'Say "hello"']
    assert result == expected

    # Test Windows-style double quotes within double quotes
    result = split_arguments('echo "Say ""hello"""', platform='win32')
    expected = ["echo", 'Say "hello"']
    assert result == expected

    # Test that single quotes are treated literally on Windows
    result = split_arguments("echo 'hello world'", platform='win32')
    expected = ["echo", "'hello", "world'"]
    assert result == expected


def test_extract_options():
    line = "command /a /b /c:1 /d:abc /flag value1 value2"
    options = ("/a", "/b", "/c", "/d", "/flag")

    args, opts = extract_options(split_arguments(line), *options)
    assert args == ["command", "value1", "value2"]
    assert opts == {"a": True, "b": True, "c": "1", "d": "abc", "flag": True}


def test_extract_options_with_no_options():
    line = "command value1 value2"
    options = ("/a", "/b", "/flag")

    args, opts = extract_options(split_arguments(line), *options)
    assert args == ["command", "value1", "value2"]
    assert opts == {}


def test_extract_options_with_some_options():
    line = "command /a value1 /flag value2"
    options = ("/a", "/b", "/flag")

    args, opts = extract_options(split_arguments(line), *options)
    assert args == ["command", "value1", "value2"]
    assert opts == {"a": True, "flag": True}


def test_extract_options_case_insensitive():
    line = "command /A /B /FLAG value1 value2"
    options = ("/a", "/b", "/flag")

    args, opts = extract_options(split_arguments(line), *options)
    assert args == ["command", "value1", "value2"]
    assert opts == {"a": True, "b": True, "flag": True}


def test_extract_options_with_unexpected_options():
    line = "command /x /y value1 value2"
    options = ("/a", "/b", "/flag")

    args, opts = extract_options(split_arguments(line), *options)
    assert args == ["command", "/x", "/y", "value1", "value2"]
    assert opts == {}
