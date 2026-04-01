"""Pass 3: Compositional verification via dependency graph traversal."""

from __future__ import annotations

from certus.spec.schema import Certificate
from certus.checker.report import DependencyResult


def check_composition(
    cert: Certificate,
    registry: dict[str, Certificate],
    _visited: set[str] | None = None,
) -> list[DependencyResult]:
    if cert.depends_on is None:
        return []

    if _visited is None:
        _visited = set()

    results: list[DependencyResult] = []

    for dep in cert.depends_on:
        if not dep.certified:
            results.append(
                DependencyResult(
                    function=dep.function,
                    status="assumed",
                    uses_valid=True,
                )
            )
            continue

        if dep.function in _visited:
            results.append(
                DependencyResult(
                    function=dep.function,
                    status="circular",
                    uses_valid=False,
                )
            )
            continue

        dep_cert = registry.get(dep.function)
        if dep_cert is None:
            results.append(
                DependencyResult(
                    function=dep.function,
                    status="not_found",
                    uses_valid=False,
                )
            )
            continue

        dep_guarantees: set[str] = set()
        for post in dep_cert.postconditions:
            dep_guarantees.update(post.guarantees)

        uses_valid = all(u in dep_guarantees for u in dep.uses)
        results.append(
            DependencyResult(
                function=dep.function,
                status="verified",
                uses_valid=uses_valid,
            )
        )

        _visited.add(cert.function)
        sub_results = check_composition(dep_cert, registry, _visited)
        for sr in sub_results:
            if sr.status == "circular":
                results.append(
                    DependencyResult(
                        function=sr.function,
                        status="circular",
                        uses_valid=False,
                    )
                )
                break
            if sr.status == "not_found" or not sr.uses_valid:
                results.append(
                    DependencyResult(
                        function=dep.function,
                        status="unverified",
                        uses_valid=False,
                    )
                )
                break

    return results
