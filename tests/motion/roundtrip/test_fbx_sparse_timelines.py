import pytest

from motion2sheet.motion.roundtrip.fbx_curve_diagnostics import (
    complete_missing_transform_curve_diagnostics,
    validate_fbx_curve_samples,
)
from motion2sheet.motion.roundtrip.native_timing import build_sample_key_times


def _stack():
    return {
        "Lcl Translation": [1.0, 2.0, 3.0],
        "Lcl Rotation": [4.0, 5.0, 6.0],
        "Lcl Scaling": [1.0, 1.0, 1.0],
    }


def _curve(bone, prop, axis, times, values):
    return {
        "bone": bone,
        "property": prop,
        "axis": axis,
        "keyTimes": times,
        "keyValues": values,
    }


def test_dense_curves_keep_uniform_stack_timeline():
    assert build_sample_key_times(0, 300, 4) == [0, 100, 200, 300]


def test_canonical_timeline_rounding_is_deterministic_and_endpoint_exact():
    assert build_sample_key_times(0, 10, 4) == [0, 3, 7, 10]


def test_sparse_and_one_key_curves_remain_raw_diagnostics():
    canonical = build_sample_key_times(0, 300, 4)
    dense = _curve("Hips", "translation", "x", [0, 100, 200, 300], [0.0, 1.0, 2.0, 3.0])
    sparse = _curve("Hips", "rotation", "z", [0, 150, 300], [4.0, 5.0, 6.0])
    one_key = _curve("Hips", "scale", "x", [0], [1.0])
    result = complete_missing_transform_curve_diagnostics(
        [dense, sparse, one_key],
        {"Hips": _stack()},
        canonical,
    )
    by_channel = {(item["property"], item["axis"]): item for item in result}

    assert by_channel[("translation", "x")] == dense
    assert by_channel[("rotation", "z")] == sparse
    assert by_channel[("scale", "x")] == one_key
    assert by_channel[("translation", "y")]["keyTimes"] == canonical
    assert by_channel[("translation", "y")]["keyValues"] == [2.0] * 4


def test_single_frame_timeline_uses_local_start():
    assert build_sample_key_times(-25, 80, 1) == [-25]


def test_timeline_fails_when_span_cannot_be_strictly_increasing():
    with pytest.raises(ValueError, match="strictly increasing"):
        build_sample_key_times(0, 2, 4)


def test_non_increasing_raw_curve_fails_closed():
    with pytest.raises(RuntimeError, match="non-increasing KeyTime"):
        validate_fbx_curve_samples([0, 200, 100, 300], [0.0, 1.0, 2.0, 3.0], label="Arm Z")


def test_raw_curve_key_value_length_mismatch_fails_closed():
    with pytest.raises(RuntimeError, match="invalid key arrays"):
        validate_fbx_curve_samples([0, 100, 200], [1.0, 2.0], label="Arm Z")


def test_non_finite_raw_curve_value_fails_closed():
    with pytest.raises(RuntimeError, match="non-finite"):
        validate_fbx_curve_samples([0, 100], [1.0, float("nan")], label="Arm Z")
