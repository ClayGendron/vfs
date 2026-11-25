"""How many etags of the spec's shape a type-guessing reader would take for a number. No server is used.

Decision 2 of the etag spec rejects base64url because 318 of 20,000
minted values began with ``-`` and would read as an option on a command
line. The same question is asked here of the form it chose: twenty
lowercase hexadecimal characters. A value made only of digits is an
integer to YAML, to a spreadsheet and to a shell arithmetic context, and
digits around one ``e`` are a float. The probe mints 400,000 etags as
decision 2 writes the mint and counts those ``int()`` accepts and those
``float()`` accepts, and prints the expected rates beside them.

    uv run python agents/2026-11-22-a-row-carries-an-etag-and-a-change-can-require-it/probes/p09_how_often_an_etag_reads_as_a_number.py
"""

from __future__ import annotations

import os

from p05_the_entry_id_as_bytes_and_the_mint import EtagMint

MINTS = 400_000


def reads_as(parse: type, value: str) -> bool:
    try:
        parse(value)
    except ValueError:
        return False
    return True


def main() -> None:
    mint = EtagMint("01JDK5Z3M7Q8R9S0T1V2W3X4Y5")
    etags = [mint.mint(os.urandom(16), 1) for _ in range(MINTS)]
    integers = sum(reads_as(int, etag) for etag in etags)
    floats = sum(reads_as(float, etag) for etag in etags)
    dashes = sum(etag.startswith("-") for etag in etags)
    all_digits = (10 / 16) ** 20
    one_e = 18 * (10 / 16) ** 19 * (1 / 16)
    print(f"{MINTS} etags minted")
    print(f"  begin with '-':            {dashes}")
    print(f"  int() accepts:             {integers}   (expected {all_digits * MINTS:.1f}, one in {1 / all_digits:,.0f})")
    print(f"  float() accepts:           {floats}   (expected {(all_digits + one_e) * MINTS:.1f}, one in {1 / (all_digits + one_e):,.0f})")
    print(f"  at 5,600,000 rows a day:   about {(all_digits + one_e) * 5_600_000:,.0f} such etags a day")


if __name__ == "__main__":
    main()
