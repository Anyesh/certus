import pytest
from certus.pipeline.collector import CodeSample, MBPPCollector


def test_code_sample_creation():
    sample = CodeSample(
        source="mbpp",
        task_id="1",
        description="Write a function to find the minimum cost path.",
        code="def min_cost(cost, m, n):\n    return cost[m][n]",
        test_code="assert min_cost([[1,2],[3,4]], 1, 1) == 4",
    )
    assert sample.source == "mbpp"
    assert "min_cost" in sample.code


def test_code_sample_has_function_name():
    sample = CodeSample(
        source="mbpp",
        task_id="1",
        description="Write a function to add two numbers.",
        code="def add(a, b):\n    return a + b",
        test_code="assert add(1, 2) == 3",
    )
    assert sample.function_name == "add"


def test_code_sample_function_name_none_if_no_def():
    sample = CodeSample(
        source="mbpp",
        task_id="1",
        description="Compute something.",
        code="x = 1 + 2",
        test_code="assert x == 3",
    )
    assert sample.function_name is None


class TestMBPPCollector:
    def test_collector_creates(self):
        collector = MBPPCollector(max_samples=5)
        assert collector.max_samples == 5

    def test_collect_returns_code_samples(self):
        collector = MBPPCollector(max_samples=3)
        samples = collector.collect()
        assert len(samples) <= 3
        assert all(isinstance(s, CodeSample) for s in samples)

    def test_collected_samples_have_required_fields(self):
        collector = MBPPCollector(max_samples=3)
        samples = collector.collect()
        for s in samples:
            assert s.source == "mbpp"
            assert s.description
            assert s.code
            assert s.task_id

    def test_collected_samples_have_functions(self):
        collector = MBPPCollector(max_samples=10)
        samples = collector.collect()
        with_functions = [s for s in samples if s.function_name is not None]
        assert len(with_functions) > 0
