"""Seed corpus of (query, expected path-prefix) benchmark cases for smart
search ranking quality. Grows organically: add a case here whenever a live
query surfaces a bad result -- see docs/superpowers/specs/
2026-07-22-smart-search-benchmark-corpus-design.md."""
from pydantic import BaseModel

DEFAULT_TOP_N = 10


class BenchmarkCase(BaseModel):
    query: str
    expected_prefixes: list[str]
    top_n: int | None = None


CASES: list[BenchmarkCase] = [
    BenchmarkCase(
        query="MMS spacecraft 1 magnetic field",
        expected_prefixes=["root speasy cda MMS MMS1 FGM", "root speasy cda MMS MMS1 SCM"],
    ),
    BenchmarkCase(
        query="MMS1 spacecraft magnetic field",
        expected_prefixes=["root speasy cda MMS MMS1 FGM", "root speasy cda MMS MMS1 SCM"],
    ),
    BenchmarkCase(
        query="MMS1 Search Coil",
        expected_prefixes=["root speasy cda MMS MMS1 SCM"],
    ),
    BenchmarkCase(
        query="MMS1 trajectory",
        expected_prefixes=["root speasy cda MMS MMS1 MEC"],
    ),
    BenchmarkCase(
        query="MMS1 ephemeris",
        expected_prefixes=["root speasy cda MMS MMS1 MEC"],
    ),
    BenchmarkCase(
        query="MMS1 electrons",
        expected_prefixes=["root speasy cda MMS MMS1 DES"],
    ),
    BenchmarkCase(
        query="ACE trajectory",
        expected_prefixes=["root speasy amda Parameters ACE Ephemeris"],
    ),
]
