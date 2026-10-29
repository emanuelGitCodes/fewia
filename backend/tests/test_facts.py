from app.agent.facts import Fact, collect_facts


def test_collect_facts_walks_depth_first_with_paths() -> None:
    payload = {
        "id": "abc",
        "meals": [
            {"servings": 2, "per_serving": {"energy_kcal": 500}},
            {"servings": 1},
        ],
        "cap": None,
        "ok": True,
        "ratio": 1.5,
    }
    assert collect_facts("get_plan", payload) == [
        Fact("get_plan", "meals[0].servings", 2),
        Fact("get_plan", "meals[0].per_serving.energy_kcal", 500),
        Fact("get_plan", "meals[1].servings", 1),
    ]


def test_collect_facts_skips_bool_none_and_non_containers() -> None:
    assert collect_facts("t", {"a": True, "b": None, "c": "7"}) == []
    assert collect_facts("t", "text") == []
    assert collect_facts("t", {"n": [3, [4]]}) == [
        Fact("t", "n[0]", 3),
        Fact("t", "n[1][0]", 4),
    ]
