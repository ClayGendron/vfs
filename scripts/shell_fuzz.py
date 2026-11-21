"""The differential fuzzer: scripts made from bash's grammar, each run by the shell and by bash.

Each run generates scripts of the language tier from a seed, records what the pinned bash does
with them through the recorder (``scripts/shell_record.py``), and judges the shell against those
records with the crate's ``judge`` example. Every disagreement is written into the corpus as a
case under ``tests/shell/cases/found/``, script and record together, and stays there. The fuzzer
runs outside the gate; it needs Docker, as the recorder does.

    uv run python scripts/shell_fuzz.py --seed 1 --count 500
    uv run python scripts/shell_fuzz.py --seed 1 --count 500 --keep   # also write what it found

A script is a function of its seed and its index, so a run can be repeated exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import shell_record

ROOT = Path(__file__).resolve().parent.parent
FOUND = ROOT / "tests" / "shell" / "cases" / "found"
JUDGE_TIMEOUT_SECONDS = 1800
KILLED_STATUS = 137

NAMES = ("a", "b", "x", "i", "s")
WORDS = ("one", "two words", "", "a*b", "x-y", "  pad  ", "tab\tin", "3", "-7", "é", "a/b/c", "*.txt")
PATTERNS = ("*", "?", "a*", "*b", "[ab]*", "o*e", "t?o", "*/*", "x-*")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def script(seed: int, index: int) -> str:
    """One script of the language tier, a function of ``seed`` and ``index``."""
    rng = random.Random(f"{seed}:{index}")
    lines = [_statement(rng, depth=0) for _ in range(rng.randint(3, 8))]
    return "# tier: language\n# world: none\n" + "\n".join(lines) + "\n"


def _statement(rng: random.Random, depth: int) -> str:
    choices = [_assign, _echo, _printf, _array, _arith, _regex, _positional, _assoc, _ifs_read, _printf_v]
    if depth < 2:
        choices += [_if, _for, _while, _case, _function, _subshell, _pipeline, _redirect, _glob, _loop_control]
    if depth == 0:
        # A here-document's delimiter must end its line, which only a top-level statement does.
        choices.append(_heredoc)
    return rng.choice(choices)(rng, depth)


def _word(rng: random.Random) -> str:
    """A word in one of bash's quotings, or an expansion."""
    kind = rng.randrange(9)
    text = rng.choice(WORDS)
    if kind == 0:
        return "'" + text.replace("'", "") + "'"
    if kind == 1:
        return '"' + text.replace('"', "").replace("$", "").replace("`", "").replace("\\", "") + '"'
    if kind == 2:
        return "$'" + text.replace("'", "").replace("\\", "").replace("\t", "\\t") + "'"
    if kind in (3, 4):
        return '"' + _expansion(rng) + '"'
    if kind == 5:
        return _expansion(rng)
    if kind == 6:
        return '"$(' + "echo " + _word_plain(rng) + ')"'
    return _word_plain(rng)


def _word_plain(rng: random.Random) -> str:
    return rng.choice(("one", "two", "x", "3", "-1", "a.b", "end"))


def _expansion(rng: random.Random) -> str:
    name = rng.choice(NAMES)
    pattern = rng.choice(PATTERNS)
    forms = (
        f"${name}",
        f"${{{name}:-dflt}}",
        f"${{{name}-dflt}}",
        f"${{{name}:+alt}}",
        f"${{#{name}}}",
        f"${{{name}#{pattern}}}",
        f"${{{name}##{pattern}}}",
        f"${{{name}%{pattern}}}",
        f"${{{name}%%{pattern}}}",
        f"${{{name}/{pattern}/R}}",
        f"${{{name}//{pattern}/R}}",
        f"${{{name}^^}}",
        f"${{{name},}}",
        f"${{{name}:1}}",
        f"${{{name}:1:2}}",
        f"${{{name}: -2}}",
        "${arr[@]}",
        "${#arr[@]}",
        "${arr[1]}",
        "${!arr[@]}",
        f"$(( {_arith_expr(rng, 0)} ))",
    )
    return rng.choice(forms)


def _arith_expr(rng: random.Random, depth: int) -> str:
    if depth > 2 or rng.random() < 0.4:
        return rng.choice(("1", "2", "7", "-3", "i", "x", "0", "10"))
    op = rng.choice(("+", "-", "*", "/", "%", "<<", "&", "|", "^", "<", "==", "!=", "&&", "||", "?"))
    left, right = _arith_expr(rng, depth + 1), _arith_expr(rng, depth + 1)
    if op == "?":
        return f"({left} ? {right} : 4)"
    if op in ("/", "%"):
        return f"({left} {op} ({right} == 0 ? 1 : {right}))"
    return f"({left} {op} {right})"


def _assign(rng: random.Random, depth: int) -> str:
    return f"{rng.choice(NAMES)}={_word(rng)}"


def _echo(rng: random.Random, depth: int) -> str:
    flag = rng.choice(("", "", "-n ", "-e "))
    words = " ".join(_word(rng) for _ in range(rng.randint(1, 3)))
    return f"echo {flag}{words}" + ("; echo" if flag == "-n " else "")


def _printf(rng: random.Random, depth: int) -> str:
    fmt = rng.choice(("'%s|'", "'[%5s]'", "'%-4s:'", "'%d\\n'", "'%q\\n'", "'%x %o\\n'", "'%s %s\\n'", "'%.2s\\n'"))
    args = " ".join(_word(rng) for _ in range(rng.randint(1, 3)))
    if "%d" in fmt or "%x" in fmt:
        args = " ".join(rng.choice(("1", "42", "-5", "0x1f", "010")) for _ in range(rng.randint(1, 2)))
    return f"printf {fmt} {args}; echo"


def _array(rng: random.Random, depth: int) -> str:
    items = " ".join(_word(rng) for _ in range(rng.randint(0, 4)))
    tail = rng.choice(("", "; arr+=(more)", "; unset 'arr[1]'", "; arr[5]=five"))
    return f'arr=({items}){tail}; printf \'<%s>\' "${{arr[@]}}"; echo " ${{#arr[@]}}"'


def _arith(rng: random.Random, depth: int) -> str:
    name = rng.choice(NAMES)
    return f'{name}=$(( {_arith_expr(rng, 0)} )); echo "{name}=${name}"'


def _condition(rng: random.Random) -> str:
    kind = rng.randrange(5)
    left, right = _word(rng), _word(rng)
    if kind == 0:
        return f"[[ {left} == {rng.choice(PATTERNS)} ]]"
    if kind == 1:
        return f"[[ -n {left} && {right} != x ]]"
    if kind == 2:
        return f"(( {_arith_expr(rng, 0)} ))"
    if kind == 3:
        return f"[ {left} = {right} ]"
    return f"[[ {left} < {right} ]]"


def _block(rng: random.Random, depth: int) -> str:
    return "; ".join(_statement(rng, depth + 1) for _ in range(rng.randint(1, 3)))


def _if(rng: random.Random, depth: int) -> str:
    otherwise = f"; else {_block(rng, depth)}" if rng.random() < 0.5 else ""
    return f'if {_condition(rng)}; then {_block(rng, depth)}{otherwise}; fi; echo "if=$?"'


def _for(rng: random.Random, depth: int) -> str:
    items = rng.choice(("1 2 3", '"${arr[@]}"', "$x", "a b", '"$s"', "{1..3}", "x{a,b}y"))
    return f'for v in {items}; do echo "[$v]"; {_block(rng, depth)}; done'


def _while(rng: random.Random, depth: int) -> str:
    # A counter of its own at each depth, so no statement inside the loop can reset it.
    bound, counter = rng.randint(0, 4), f"n{depth}"
    block = _block(rng, depth)
    step = f"{counter}=$(({counter} + 1))"
    return f'{counter}=0; while (( {counter} < {bound} )); do {step}; {block}; done; echo "{counter}=${counter}"'


def _case(rng: random.Random, depth: int) -> str:
    arms = " ".join(f"{rng.choice(PATTERNS)}) echo arm{n};;" for n in range(rng.randint(1, 3)))
    return f"case {_word(rng)} in {arms} *) echo none;; esac"


def _function(rng: random.Random, depth: int) -> str:
    name = rng.choice(("f", "g"))
    body = _block(rng, depth)
    call = " ".join(_word(rng) for _ in range(rng.randint(0, 2)))
    return f'{name}() {{ local s="$1"; {body}; echo "args=$#"; return 3; }}; {name} {call}; echo "ret=$?"'


def _subshell(rng: random.Random, depth: int) -> str:
    return f'( {_block(rng, depth)}; x=inner ); echo "x=$x"'


def _pipeline(rng: random.Random, depth: int) -> str:
    left = rng.choice(("echo one two", "printf 'a\\nb\\n'", 'echo "$x"'))
    right = rng.choice(('while read -r w; do echo "<$w>"; done', '{ read -r first; echo "first=$first"; }', "cat"))
    if right == "cat":
        right = '{ read -r l; echo "$l"; }'
    return f'{left} | {right}; echo "pipe=$?"'


def _redirect(rng: random.Random, depth: int) -> str:
    op = rng.choice((">", ">>"))
    return f'{{ {_block(rng, depth)}; }} {op} out.txt; while read -r l; do echo "r:$l"; done < out.txt'


def _heredoc(rng: random.Random, depth: int) -> str:
    quoted = rng.random() < 0.5
    delim = "'EOF'" if quoted else "EOF"
    return f'while read -r l; do echo "h:$l"; done <<{delim}\n{_word(rng)} {_expansion(rng)}\nplain $x\nEOF'


def _regex(rng: random.Random, depth: int) -> str:
    # Each one bash parses: a blank is part of the word only inside a group.
    regex = rng.choice(("^t(w)o", "([a-z]+)( [a-z]+)?", "[0-9]+$", "^$", "(a|b)+", "x-?y", "^[^x]*", "(two w|on)"))
    matched = 'echo "m=${BASH_REMATCH[0]}|${BASH_REMATCH[1]}"'
    return f"if [[ {_word(rng)} =~ {regex} ]]; then {matched}; else echo nomatch; fi"


def _positional(rng: random.Random, depth: int) -> str:
    words = " ".join(_word(rng) for _ in range(rng.randint(0, 4)))
    use = rng.choice(
        (
            'printf "[%s]" "$@"; echo',
            'echo "$#:$*"',
            'shift; echo "$1|$#"',
            'echo "${@:2}"',
            'IFS=:; echo "$*"; unset IFS',
        )
    )
    return f"set -- {words}; {use}"


def _assoc(rng: random.Random, depth: int) -> str:
    keys = rng.sample(("k", "two", "3", "x y", "é"), k=rng.randint(1, 3))
    pairs = " ".join(f'["{key}"]={_word(rng)}' for key in keys)
    use = rng.choice(
        (
            'echo "${#m[@]}"',
            'echo "${m[k]-unset}"',
            'for key in "${!m[@]}"; do echo "$key"; done | { read -r a; echo got; }',
        )
    )
    return f"declare -A m=({pairs}); {use}"


def _ifs_read(rng: random.Random, depth: int) -> str:
    sep = rng.choice((",", ":", " ", "-"))
    text = sep.join(rng.choice(("a", "", "b c", "d")) for _ in range(rng.randint(1, 4)))
    return f'IFS="{sep}" read -r p q r <<< "{text}"; echo "p=$p q=$q r=$r"'


def _printf_v(rng: random.Random, depth: int) -> str:
    return f"printf -v {rng.choice(NAMES)} '%s-%s' {_word(rng)} {_word(rng)}; echo \"${rng.choice(NAMES)}\""


def _glob(rng: random.Random, depth: int) -> str:
    files = " ".join(f": > {name};" for name in rng.sample(("a.txt", "b.txt", "ab", ".hidden", "c d"), k=3))
    pattern = rng.choice(("*.txt", "?b", "*", "[ab]*", "*.none", ".*"))
    options = rng.choice(("", "shopt -s nullglob; ", "shopt -s dotglob; ", "shopt -s failglob; "))
    return f'{files} {options}for f in {pattern}; do echo "g:$f"; done; shopt -u nullglob dotglob failglob'


def _loop_control(rng: random.Random, depth: int) -> str:
    control = rng.choice(("break", "continue", "break 1"))
    test = f"if (( v == {rng.randint(1, 4)} )); then {control}; fi"
    return f'for v in 1 2 3 4; do {test}; echo "c:$v"; done; echo "after=$v"'


# ---------------------------------------------------------------------------
# A run
# ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--keep", action="store_true", help="write each disagreement into tests/shell/cases/found/")
    parser.add_argument("--work", type=Path, help="generate into this directory and leave it, to read the cases")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as scratch:
        root = (args.work or Path(scratch)) / "cases"
        shutil.rmtree(root, ignore_errors=True)
        names = []
        for index in range(args.count):
            name = f"fuzz/s{args.seed}-{index:05d}"
            path = root / f"{name}.sh"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(script(args.seed, index))
            names.append(name)
        unstable = shell_record.record(names, root)
        unfinished = [name for name in names if name not in unstable and _killed(root, name)]
        for name in [*unstable, *unfinished]:
            (root / f"{name}.sh").unlink()
            (root / f"{name}.json").unlink(missing_ok=True)
        differing = _judge(root)
        dropped = f"{len(unstable)} unstable, {len(unfinished)} unfinished"
        sys.stdout.write(f"seed {args.seed}: {args.count} scripts, {dropped}, {len(differing)} differ\n")
        for name, why in differing.items():
            sys.stdout.write(f"  {name}: {why.splitlines()[0] if why else ''}\n")
        if args.keep:
            for name in differing:
                _keep(root, name)
    return 0


def _judge(root: Path) -> dict[str, str]:
    """The cases under ``root`` the shell does not answer as bash recorded, with why."""
    done = subprocess.run(
        ["cargo", "run", "-q", "--release", "-p", "vfs-shell", "--example", "judge", "--", str(root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=JUDGE_TIMEOUT_SECONDS,
    )
    differing: dict[str, str] = {}
    current = None
    for line in done.stdout.splitlines():
        if line.startswith("DIFFER "):
            current = line.removeprefix("DIFFER ")
            differing[current] = ""
        elif current is not None and line.startswith("    ") and not differing[current]:
            differing[current] = line.strip()
    return differing


def _killed(root: Path, name: str) -> bool:
    """Whether bash was stopped by the recorder's timeout rather than finishing the script."""
    return json.loads((root / f"{name}.json").read_text())["status"] == KILLED_STATUS


def _keep(root: Path, name: str) -> None:
    """Write one disagreement into the corpus, named by its script's hash so a rerun adds no twin."""
    source = (root / f"{name}.sh").read_text()
    digest = hashlib.sha256(source.encode()).hexdigest()[:12]
    FOUND.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / f"{name}.sh", FOUND / f"{digest}.sh")
    shutil.copyfile(root / f"{name}.json", FOUND / f"{digest}.json")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
