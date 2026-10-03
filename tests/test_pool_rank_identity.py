"""Regression: the documented identity tie-break must be ascending."""

from foreshadow.pipeline.compare import assign_pool_ranks, assign_pool_ranks_v2
from test_select import passing


def test_equal_scores_use_identity_ascending_independent_of_collection_order():
    a = passing("owner-a", "repo", 80)
    b = passing("owner-b", "repo", 80)
    first = [(b, {"node_id": "B", "S": 100}), (a, {"node_id": "A", "S": 100})]
    second = list(reversed(first))
    for rank in (assign_pool_ranks, assign_pool_ranks_v2):
        assert rank(first) == {"A": 1, "B": 2}
        assert rank(second) == {"A": 1, "B": 2}
