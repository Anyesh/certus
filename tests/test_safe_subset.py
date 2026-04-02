import pytest
from certus.spec.safe_subset import validate_expression, UnsafeExpressionError


class TestAllowedExpressions:
    def test_simple_comparison(self):
        validate_expression("result > 0")

    def test_boolean_operators(self):
        validate_expression("result > 0 and result < 100")

    def test_arithmetic(self):
        validate_expression("result == a + b")

    def test_membership(self):
        validate_expression("x in result")

    def test_allowed_builtins(self):
        validate_expression("len(result) == len(a) + len(b)")

    def test_sorted(self):
        validate_expression("result == sorted(result)")

    def test_all_any(self):
        validate_expression("all(x > 0 for x in result)")

    def test_set_operations(self):
        validate_expression("set(result) == set(a) | set(b)")

    def test_subscript(self):
        validate_expression("result[0] == a[0]")

    def test_slicing(self):
        validate_expression("result[:k] == sorted(result[:k])")

    def test_list_comprehension(self):
        validate_expression("[x for x in result if x > 0]")

    def test_isinstance(self):
        validate_expression("isinstance(result, list)")

    def test_chained_comparison(self):
        validate_expression("0 <= self.tokens <= self.capacity")

    def test_min_max(self):
        validate_expression("result == min(a, b)")

    def test_sum_abs(self):
        validate_expression("sum(result) == abs(total)")

    def test_tuple_range(self):
        validate_expression(
            "all(result[i] <= result[i+1] for i in range(len(result)-1))"
        )

    def test_attribute_access(self):
        validate_expression("self.tokens >= 0")

    def test_old_expr(self):
        validate_expression("self.tokens >= old(self.tokens)")

    def test_result_keyword(self):
        validate_expression("result is True")

    def test_none_check(self):
        validate_expression("result is not None")

    def test_type_builtin(self):
        validate_expression("type(result) == list")


class TestForbiddenExpressions:
    def test_import(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("__import__('os')")

    def test_eval(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("eval('1+1')")

    def test_exec(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("exec('x=1')")

    def test_open(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("open('/etc/passwd')")

    def test_print(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("print(result)")

    def test_getattr(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("getattr(result, 'x')")

    def test_setattr(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("setattr(result, 'x', 1)")

    def test_globals(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("globals()")

    def test_locals(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("locals()")

    def test_compile(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("compile('x', '', 'eval')")

    def test_walrus_operator(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("(x := 5) > 0")

    def test_unknown_function_call(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("my_custom_func(result)")

    def test_lambda(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("(lambda x: x)(result)")

    def test_dunder_method(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("result.__class__.__bases__")

    def test_syntax_error(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("result ===")

    def test_empty_expression(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("")

    def test_input(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("input('prompt')")

    def test_delattr(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("delattr(obj, 'x')")

    def test_breakpoint(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("breakpoint()")

    def test_f_string(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("f'{result}'")

    def test_forbidden_method_unknown(self):
        with pytest.raises(UnsafeExpressionError):
            validate_expression("x.dangerous_method()")

    def test_forbidden_method_on_module(self):
        # "system" is not in ALLOWED_METHODS
        with pytest.raises(UnsafeExpressionError):
            validate_expression("obj.system('cmd')")


class TestMethodCalls:
    """Tests for allowed method call support."""

    def test_str_split(self):
        validate_expression("result.split()")

    def test_str_split_with_arg(self):
        validate_expression("result.split(',')")

    def test_str_lower(self):
        validate_expression("result.lower()")

    def test_str_upper(self):
        validate_expression("result.upper()")

    def test_str_replace(self):
        validate_expression("result.replace(' ', '_')")

    def test_str_startswith(self):
        validate_expression("result.startswith('prefix')")

    def test_str_strip(self):
        validate_expression("result.strip()")

    def test_str_count(self):
        validate_expression("result.count('x')")

    def test_str_isdigit(self):
        validate_expression("result.isdigit()")

    def test_str_join(self):
        validate_expression("' '.join(result)")

    def test_dict_values(self):
        validate_expression("result.values()")

    def test_dict_keys(self):
        validate_expression("result.keys()")

    def test_dict_items(self):
        validate_expression("result.items()")

    def test_dict_get(self):
        validate_expression("result.get('key', 0)")

    def test_list_copy(self):
        validate_expression("result.copy()")

    def test_set_union(self):
        validate_expression("set(a).union(set(b))")

    def test_set_intersection(self):
        validate_expression("set(a).intersection(set(b))")

    def test_chained_method_in_comprehension(self):
        validate_expression("all(x.isdigit() for x in result)")

    def test_method_on_subscript(self):
        validate_expression("result[0].lower()")

    def test_nested_method_calls(self):
        validate_expression("len(result.split(','))")

    def test_method_in_comparison(self):
        validate_expression("result.count('a') > 0")

    def test_sum_dict_values(self):
        validate_expression("sum(result.values()) == len(list1)")
