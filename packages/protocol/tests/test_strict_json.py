"""Unit tests for the reference strict-JSON parser: the cases a JSON vector cannot carry.

The accept/reject vectors live in examples/v1/parse/ and are run by test_schemas.py. These
tests cover what a text file cannot: bytes that are not UTF-8, sizes at the exact byte limit,
and inputs that stress the parser itself.
"""

import json

import pytest
from protocol_strict_json import (
    MAX_INTEGER,
    MAX_JSON_DEPTH,
    MAX_MESSAGE_BYTES,
    REASONS,
    ProfileError,
    parse_strict,
)


def reason_of(data):
    with pytest.raises(ProfileError) as info:
        parse_strict(data)
    assert info.value.reason in REASONS
    return info.value.reason


def padded(total_bytes):
    """A valid one-key object of exactly `total_bytes` bytes."""
    overhead = len(b'{"a":""}')
    return '{"a":"' + "x" * (total_bytes - overhead) + '"}'


def test_a_message_of_exactly_the_byte_limit_parses():
    text = padded(MAX_MESSAGE_BYTES)
    assert len(text.encode()) == MAX_MESSAGE_BYTES
    assert parse_strict(text)["a"].startswith("x")


def test_one_byte_over_the_limit_is_rejected_before_parsing():
    assert reason_of(padded(MAX_MESSAGE_BYTES + 1)) == "size_exceeded"


def test_the_limit_counts_bytes_not_characters():
    two_byte = '{"a":"' + "é" * (MAX_MESSAGE_BYTES // 2) + '"}'
    assert len(two_byte) < MAX_MESSAGE_BYTES < len(two_byte.encode())
    assert reason_of(two_byte) == "size_exceeded"


def test_bytes_input_is_accepted_and_checked_the_same_way():
    assert parse_strict(b'{"a":1}') == {"a": 1}
    assert reason_of(padded(MAX_MESSAGE_BYTES + 1).encode()) == "size_exceeded"


@pytest.mark.parametrize(
    "data",
    [b'{"a":"\xff"}', b'{"a":"\xc3"}', b'{"a":"\xed\xa0\x80"}', b"\xef\xbb\xbf{}"[1:]],
    ids=["invalid-byte", "truncated-sequence", "encoded-surrogate", "partial-bom"],
)
def test_bytes_that_are_not_utf8_are_rejected(data):
    assert reason_of(data) == "invalid_utf8"


def test_a_byte_order_mark_is_rejected():
    assert reason_of(b"\xef\xbb\xbf{}") == "invalid_json"


def test_a_lone_surrogate_character_in_a_str_cannot_be_encoded():
    assert reason_of('{"a":"\ud800"}') == "invalid_utf8"


def test_absurdly_long_digit_strings_are_out_of_range_not_a_crash():
    assert reason_of('{"a":' + "9" * 5000 + "}") == "integer_out_of_range"


def test_integer_limits_are_exact():
    assert parse_strict(f'{{"a":{MAX_INTEGER}}}')["a"] == MAX_INTEGER
    assert parse_strict(f'{{"a":-{MAX_INTEGER}}}')["a"] == -MAX_INTEGER
    assert reason_of(f'{{"a":{MAX_INTEGER + 1}}}') == "integer_out_of_range"
    assert reason_of(f'{{"a":-{MAX_INTEGER + 1}}}') == "integer_out_of_range"


def test_a_float_that_is_integral_may_exceed_the_integer_limit_but_stays_finite():
    assert parse_strict('{"a":1e20}')["a"] == 1e20


def test_nesting_stops_at_the_limit_without_exhausting_the_stack():
    at_limit = '{"a":' + "[" * (MAX_JSON_DEPTH - 1) + "]" * (MAX_JSON_DEPTH - 1) + "}"
    assert parse_strict(at_limit)
    assert (
        reason_of('{"a":' + "[" * MAX_JSON_DEPTH + "]" * MAX_JSON_DEPTH + "}") == "depth_exceeded"
    )
    deep = '{"a":' + "[" * 200_000 + "]" * 200_000 + "}"
    assert reason_of(deep) == "depth_exceeded"


def test_duplicates_are_found_after_decoding_keys():
    assert reason_of('{"a":1,"\\u0061":2}') == "duplicate_key"
    assert reason_of('{"a":{"b":1,"b":2}}') == "duplicate_key"
    assert reason_of('{"a":[{"b":1,"b":2}]}') == "duplicate_key"


def test_null_is_rejected_anywhere():
    assert reason_of('{"a":null}') == "null_value"
    assert reason_of('{"a":[1,null]}') == "null_value"
    assert reason_of('{"a":{"b":{"c":null}}}') == "null_value"


def test_surrogates_are_rejected_in_keys_and_values_but_pairs_are_fine():
    assert reason_of('{"\\ud800":1}') == "lone_surrogate"
    assert reason_of('{"a":["\\udc00"]}') == "lone_surrogate"
    assert parse_strict('{"a":"\\ud83d\\ude00"}')["a"] == "\U0001f600"


def test_what_python_alone_would_accept_is_exactly_what_the_profile_refuses():
    """Documents why the profile exists: each of these parses under plain json.loads."""
    for text in ('{"a":NaN}', '{"a":Infinity}', '{"a":1e999}', '{"a":1,"a":2}', '{"a":"\\ud800"}'):
        json.loads(text)
        with pytest.raises(ProfileError):
            parse_strict(text)


def test_every_failure_has_a_reason_from_the_closed_list():
    for text in ("", "[]", "{", '{"a":01}', '{"a":NaN}', '{"a":null}', '{"a":1,"a":1}'):
        assert reason_of(text) in REASONS
