import sys

from lib.helpers import greet


def main():
    # TODO: parse arguments
    print(greet(sys.argv[1] if len(sys.argv) > 1 else "world"))


if __name__ == "__main__":
    main()
