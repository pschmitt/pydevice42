import typing as t


def int_cast(i: t.Any) -> int:
    return int(t.cast(t.SupportsInt, i))
