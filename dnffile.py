#!/usr/bin/python3

import os
import re
from typing import Any, Callable, Generator, Iterable, Optional, TypeVar
import dnf
import argparse
import hawkey
import sys
import itertools
import subprocess

T = TypeVar("T")


def and_then(x: Optional[T], f: Callable[[T], T]) -> Optional[T]:
    return f(x) if x is not None else x


def notNone(x):
    assert x is not None
    return x


def flatten(listOfList: Iterable[Iterable[T]]) -> Iterable[T]:
    return itertools.chain(*listOfList)


# TODO: transform into Iterator
def distinct(iter: Iterable[T], keyfunc=None) -> Generator[T, Any, None]:
    seen = set()
    for item in iter:
        key = item if keyfunc is None else keyfunc(item)
        if key not in seen:
            seen.add(key)
            yield item


DNFFILE_DIRECTORY: str = os.path.join(
    notNone(
        and_then(os.getenv("XDG_CONFIG_DIR"), lambda x: os.path.join(x, "dnffile"))
        or and_then(os.getenv("HOME"), lambda x: os.path.join(x, ".config", "dnffile"))
    )
)


# TODO: share sack with getAllInstalled
def getExplicitInstalled() -> Iterable[hawkey.Package]:
    base = dnf.Base()
    sack = base.fill_sack()

    installed = sack.query().installed().run()

    return filter(lambda pkg: pkg.reason != "dependency", installed)


def getAllInstalled() -> Iterable[hawkey.Package]:
    base = dnf.Base()
    sack = base.fill_sack()

    installed = sack.query().installed().run()
    return installed


def dump():
    pkgs = getExplicitInstalled()
    sys.stdout.writelines(map(lambda pkg: pkg.name + "\n", pkgs))


def readDnffile(fpath: str) -> Iterable[str]:
    print(f"file {fpath}")

    def notComment(line: str) -> bool:
        commentPattern = re.compile(r"^\s*#")
        return not commentPattern.match(line)

    with open(fpath, "r") as fh:
        return map(str.strip, filter(notComment, fh.readlines()))


def readDnfDir() -> Iterable[str]:
    """
    Reads the dnffile directory and returns all package names listed in dnffile*.txt
    """
    files = os.listdir(DNFFILE_DIRECTORY)
    pattern = re.compile(r"^dnffile.*\.txt$")
    return sorted(
        filter(
            lambda pname: pname != "",
            distinct(
                flatten(
                    map(
                        lambda f: readDnffile(os.path.join(DNFFILE_DIRECTORY, f)),
                        filter(pattern.match, files),
                    ),
                )
            ),
        )
    )


class AppState:
    def __init__(self, verbose=False):
        self.verbose = verbose

    def log(self, *args, **kwargs):
        print(*args, file=sys.stderr, **kwargs)

    def sync(self):
        # TODO: optimize: package names are sorted, to_install and to_remove can be optimize to take advantage of that
        installed = list(map(lambda x: x.name, getAllInstalled()))
        explicitly_installed = list(map(lambda x: x.name, getExplicitInstalled()))
        wanted = list(readDnfDir())
        to_install = list(filter(lambda pname: pname not in installed, wanted))

        if self.verbose:
            self.log("Installing\t", to_install)

        if len(to_install) > 0:
            cmd = subprocess.run(
                ["sudo", "dnf", "install", *to_install],
                stdout=sys.stdout,
                stderr=sys.stderr,
            )
            cmd.check_returncode()
        else:
            sys.stderr.write("nothing to install.\n")

        to_remove = list(
            filter(lambda pname: pname not in wanted, explicitly_installed)
        )
        if len(to_remove) > 0:
            subprocess.run(
                ["sudo", "dnf", "remove", *to_remove],
                stdout=sys.stdout,
                stderr=sys.stderr,
            ).check_returncode()
        else:
            sys.stderr.write("nothing to remove.\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Declarative dnf wrapper")

    command_parser = parser.add_subparsers(dest="command")
    command_parser.add_parser(
        "dump", help="Dump currently installed packages to stdout"
    )

    sync_parser = command_parser.add_parser("sync", help="Synchronise packages")

    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose")

    args = parser.parse_args()

    app = AppState(verbose=args.verbose)

    if args.command == "dump":
        dump()
    elif args.command == "sync":
        app.sync()
