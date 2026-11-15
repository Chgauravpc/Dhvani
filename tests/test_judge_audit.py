"""3B-19 (a)/(a2): the list-aware judge and the failure classifier (no network)."""

from __future__ import annotations

from dhvani.eval.datasets import ExpectedToolCall
from dhvani.eval.judge_audit import (
    MISSING_ARGUMENT,
    NO_CALL,
    PROVIDER_REJECTED,
    VALUE_MISMATCH,
    WRONG_FUNCTION,
    array_params,
    classify_failure,
    judge_list_aware,
)
from dhvani.eval.task_success import judge_tool_call
from dhvani.types import ToolCall

EXPECTED = ExpectedToolCall(
    name="recipe_search",
    arguments={
        "ingredients": ("paneer", "tomatoes", "onions"),  # array: required elements
        "dietary_restriction": ("Vegetarian", "veg"),  # scalar: alternatives
    },
)
ARRAYS = frozenset({"ingredients"})


def _call(name: str = "recipe_search", **arguments: object) -> ToolCall:
    return ToolCall(id="1", name=name, arguments=arguments)


def test_array_params_reads_the_function_schema() -> None:
    functions = [
        {
            "name": "recipe_search",
            "parameters": {
                "type": "dict",
                "properties": {
                    "ingredients": {"type": "array", "items": {"type": "string"}},
                    "dietary_restriction": {"type": "string"},
                },
            },
        },
        {"name": "other", "parameters": {"properties": {"x": {"type": "array"}}}},
    ]
    assert array_params(functions, "recipe_search") == frozenset({"ingredients"})
    assert array_params(functions, "missing") == frozenset()


def test_a_correct_list_fails_the_registered_judge_and_passes_the_fixed_one() -> None:
    call = _call(ingredients=["paneer", "tomatoes", "onions"], dietary_restriction="veg")
    assert judge_tool_call(call, EXPECTED) is False  # the bug
    assert judge_list_aware(call, EXPECTED, ARRAYS) is True


def test_list_aware_ignores_order_case_and_duplicates() -> None:
    call = _call(ingredients=["Onions", "paneer", "tomatoes", "paneer"], dietary_restriction="Veg")
    assert judge_list_aware(call, EXPECTED, ARRAYS) is True


def test_list_aware_still_fails_a_missing_or_extra_element() -> None:
    short = _call(ingredients=["paneer", "tomatoes"], dietary_restriction="veg")
    extra = _call(ingredients=["paneer", "tomatoes", "onions", "rice"], dietary_restriction="veg")
    assert judge_list_aware(short, EXPECTED, ARRAYS) is False
    assert judge_list_aware(extra, EXPECTED, ARRAYS) is False


def test_scalar_parameters_keep_alternatives_semantics() -> None:
    wrong = _call(ingredients=["paneer", "tomatoes", "onions"], dietary_restriction="vegan")
    assert judge_list_aware(wrong, EXPECTED, ARRAYS) is False


def test_a_returned_scalar_counts_as_a_one_element_list() -> None:
    single = ExpectedToolCall(name="f", arguments={"items": ("milk",)})
    assert judge_list_aware(_call("f", items="milk"), single, frozenset({"items"})) is True


def test_no_call_and_wrong_name_and_missing_argument_fail() -> None:
    assert judge_list_aware(None, EXPECTED, ARRAYS) is False
    assert judge_list_aware(_call("other"), EXPECTED, ARRAYS) is False
    assert judge_list_aware(_call(ingredients=["paneer"]), EXPECTED, ARRAYS) is False


def test_classifier_uses_the_judge_order() -> None:
    def kind(actual: ToolCall | None, err: str = "") -> str:
        return classify_failure(actual, err, EXPECTED, ARRAYS).category

    assert kind(None, "tool_validation_failed") == PROVIDER_REJECTED
    assert kind(None) == NO_CALL
    assert kind(_call("other")) == WRONG_FUNCTION
    assert kind(_call(ingredients=["paneer"])) == MISSING_ARGUMENT
    assert kind(_call(ingredients=["paneer"], dietary_restriction="veg")) == VALUE_MISMATCH


def test_value_mismatch_flags_list_and_devanagari() -> None:
    listed = classify_failure(
        _call(ingredients=["paneer", "tomatoes", "onions"], dietary_restriction="veg"),
        "",
        EXPECTED,
        ARRAYS,
    )
    assert (listed.category, listed.list_valued, listed.devanagari) == (VALUE_MISMATCH, True, False)
    deva = classify_failure(
        _call(ingredients=["paneer"], dietary_restriction="शाकाहारी"),
        "",
        EXPECTED,
        ARRAYS,
        list_aware=True,
    )
    assert deva.devanagari is True
    other = classify_failure(
        _call(ingredients=["paneer", "tomatoes", "onions"], dietary_restriction="vegan"),
        "",
        EXPECTED,
        ARRAYS,
        list_aware=True,
    )
    assert other.other is True
