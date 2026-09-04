"""Regression tests for the statistics parser desync guard (issue #262).

The machine occasionally transmits the whole statistics record block more
than once within a single notification. The fixed [ID 2B] + [Value 4B] stride
then reads phantom records (e.g. PID 53313 == the frame's own 0xD041 magic)
out of the duplicated block. The parser now keeps only the leading fragment
before a repeated statistics header.

The other historic phantom source — an unrelated notification fused onto a
statistics frame — is rejected upstream at the transport layer by the CRC
gate (failures of #245 / `_has_valid_crc`), so it is not exercised here.
"""
import asyncio
import os
import sys
from binascii import unhexlify

sys.path.append(
    os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "custom_components",
        )
    )
)

from delonghi_primadonna.device import DelongiPrimadonna  # noqa: E402
from delonghi_primadonna.device import (  # noqa: E402
    STATISTICS_RESPONSE_HEADER,
)

CONFIG = {
    "mac": "00:11:22:33:44:55",
    "model": "TEST",
    "name": "TEST",
}

# Real frames captured live from a DeLonghi Dinamica Plus on 2026-09-04.
# name, hex_frame, expected raw PIDs.
DUPLICATE_FRAMES = [
    (
        "duplicate-110",
        "d0 41 a2 0f 00 6f 00 00 00 12 00 74 00 00 06 54 06 54 00 00 "
        "d0 41 a2 0f 00 6f 00 00 00 12 00 74 00 00 06 54 06 54 00 00 00 00 "
        "0b b8 00 00 01 0a 0b b9 00 00 0d 23 0b ba 00 00 04 5f 00 00 0b b8 00 00",
        {111, 116},
    ),
    (
        "triplicate-110",
        "d0 41 a2 0f 00 6f 00 00 00 12 00 74 00 00 06 55 06 55 00 00 "
        "d0 41 a2 0f 00 6f 00 00 00 12 00 74 00 00 06 55 06 55 00 00 "
        "d0 41 a2 0f 00 6f 00 00 00 12 00 74 00 00 06 55 06 55 00 00 "
        "00 00 0b b8 00 00",
        {111, 116},
    ),
    (
        "triplicate-3000",
        "d0 41 a2 0f 0b b8 00 00 01 0a 0b b9 00 00 0d 24 0b ba 00 00 "
        "d0 41 a2 0f 0b b8 00 00 01 0a 0b b9 00 00 0d 24 0b ba 00 00 "
        "d0 41 a2 0f 0b b8 00 00 01 0a 0b b9 00 00 0d 24 0b ba 00 00 "
        "04 5f 0b bb 00 00",
        {3000, 3001},
    ),
]

CLEAN_FRAMES = [
    # The gold-standard statistics frame used by the existing test suite. It
    # has no repeated header, so the guard must leave it untouched: the
    # leading records parse to their documented values.
    (
        "clean-100",
        "d0 41 a2 0f 00 64 00 13 a8 9e 00 65 00 00 00 0a 00 69 00 00 00 0f "
        "00 6a 00 23 65 e8 00 6c 00 00 00 00 00 6d 00 00 00 00 00 6f 00 00 00 12 "
        "00 74 00 00 02 84 02 84 00 00 00 00 0b b8 00 00 39 7e 54 d1",
        {100: 1288350, 101: 10, 105: 15, 111: 18},
    ),
    (
        "clean-23000",
        "d0 1d a2 0f 59 d8 00 00 00 01 59 d9 00 00 2a 85 59 da 00 00 "
        "00 ca 59 db 00 00 00 fb 2d 99",
        {23000: 1, 23001: 10885, 23002: 202, 23003: 251},
    ),
]


async def _raw_pids(device):
    return {k for k in device.statistics if k >= 0}  # ignore derived (negative) keys


async def test_duplicated_frames_keep_only_leading_block():
    for name, hex_frame, expected in DUPLICATE_FRAMES:
        device = DelongiPrimadonna(CONFIG, None)
        data = unhexlify(hex_frame.replace(" ", ""))
        await device._parse_statistics(data)

        # Each of these frames repeats the header inside the body, so the
        # parser must have truncated and kept only the first copy.
        assert data.count(STATISTICS_RESPONSE_HEADER) > 1, name
        raw = await _raw_pids(device)
        assert raw == expected, f"{name}: got {sorted(raw)}, expected {sorted(expected)}"


async def test_clean_frames_unchanged():
    for name, hex_frame, expected in CLEAN_FRAMES:
        device = DelongiPrimadonna(CONFIG, None)
        data = unhexlify(hex_frame.replace(" ", ""))
        await device._parse_statistics(data)

        # No repeated header, so the guard never truncates: leading records
        # must parse to their documented values.
        assert data.count(STATISTICS_RESPONSE_HEADER) <= 1, name
        for pid, value in expected.items():
            assert device.statistics[pid] == value, (
                f"{name}: ID {pid} = {device.statistics.get(pid)}, "
                f"expected {value}"
            )


async def run_tests():
    await test_duplicated_frames_keep_only_leading_block()
    await test_clean_frames_unchanged()
    print("[SUCCESS] Statistics parser desync regressions verified.")


if __name__ == "__main__":
    asyncio.run(run_tests())
