from news_insight.cards.engines import EngineOutput
from news_insight.stories.evaluate import Pair, judge, score


def test_judge_batches_and_threshold_scores() -> None:
    pairs = [
        Pair(0, "a", "a2", 0.9),
        Pair(1, "b", "b2", 0.5),
        Pair(2, "c", "x", 0.3),
        Pair(3, "d", "d2", 0.28),
    ]
    calls: list[str] = []

    def ask(prompt: str, schema: dict[str, object]) -> EngineOutput:
        calls.append(prompt)
        return EngineOutput(
            raw={
                "pairs": [
                    {"id": 0, "same": True},
                    {"id": 1, "same": True},
                    {"id": 2, "same": False},
                    {"id": 3, "same": True},
                ]
            },
            model="m",
        )

    labels = judge(ask, pairs, batch=10)
    by_threshold = {s.threshold: s for s in score(pairs, labels)}

    assert len(calls) == 1 and labels == {0: True, 1: True, 2: False, 3: True}
    assert by_threshold[0.25].recall == 1.0 and by_threshold[0.25].precision == 0.75
    assert by_threshold[0.5].precision == 1.0 and by_threshold[0.5].recall == 2 / 3
