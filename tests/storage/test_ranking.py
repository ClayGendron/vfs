"""The ranking seams: per-leg normalisation, Convex against a hand-computed fusion, RRF against
its definition, the one-leg identity, determinism, value identity, and the refusals."""

from __future__ import annotations

from typing import Any, cast

import pytest

from vfs.storage.ranking import (
    LEG_NAMES,
    RRF,
    Convex,
    Fusion,
    InDegree,
    Katz,
    Linear,
    Log1p,
    MaxP,
    PageRank,
    PathShape,
    Ranker,
    Saturation,
    Sigmoid,
    Signal,
    min_max,
    unit_cosine,
)


class TestNormalisation:
    def test_unit_cosine_maps_the_theoretical_range(self) -> None:
        assert unit_cosine(-1.0) == 0.0 and unit_cosine(0.0) == 0.5 and unit_cosine(1.0) == 1.0

    def test_min_max_over_the_candidate_union(self) -> None:
        assert min_max({"a": 2.0, "b": 6.0, "c": 4.0}) == {"a": 0.0, "b": 1.0, "c": 0.5}
        assert min_max({"only": 3.0}) == {"only": 1.0}
        assert min_max({"a": 1.0, "b": 1.0}) == {"a": 1.0, "b": 1.0}
        assert min_max({}) == {}


class TestConvex:
    def test_the_reference_fusion_by_hand(self) -> None:
        legs = {"vector": {"a": 0.8, "b": 0.2}, "lexical": {"a": 0.5, "c": 1.0}}
        fused = Convex({"vector": 0.5, "lexical": 0.5}).fuse(legs)
        assert fused == {"a": pytest.approx(0.65), "b": pytest.approx(0.1), "c": pytest.approx(0.5)}
        lexical_heavy = Convex({"vector": 0.3, "lexical": 0.7}).fuse(legs)
        assert lexical_heavy["a"] == pytest.approx(0.3 * 0.8 + 0.7 * 0.5)

    def test_weights_renormalise_over_the_legs_present(self) -> None:
        one_leg = {"lexical": {"a": 0.25, "b": 1.0}}
        assert Convex({"vector": 0.9, "lexical": 0.1}).fuse(one_leg) == {"a": 0.25, "b": 1.0}
        assert Convex().fuse({}) == {}

    def test_defaults_and_identity(self) -> None:
        assert Convex().weights == {"vector": 0.5, "lexical": 0.5}
        assert Convex() == Convex({"lexical": 0.5, "vector": 0.5}) and hash(Convex()) == hash(Convex())
        assert Convex({"vector": 0.3, "lexical": 0.7}) != Convex()
        assert repr(Convex({"vector": 0.3, "lexical": 0.7})) == "Convex({'vector': 0.3, 'lexical': 0.7})"
        assert isinstance(Convex(), Fusion)

    def test_refusals(self) -> None:
        with pytest.raises(ValueError, match="unknown legs"):
            Convex({"graph": 1.0})
        with pytest.raises(ValueError, match="positive"):
            Convex({"vector": 0.0, "lexical": 1.0})
        with pytest.raises(ValueError, match="positive"):
            Convex({})


class TestRRF:
    def test_the_definition_by_hand(self) -> None:
        legs = {"vector": {"a": 0.9, "b": 0.1}, "lexical": {"b": 5.0, "a": 4.0, "c": 1.0}}
        fused = RRF(k=10).fuse(legs)
        assert fused["a"] == pytest.approx(1 / 11 + 1 / 12)
        assert fused["b"] == pytest.approx(1 / 12 + 1 / 11)
        assert fused["c"] == pytest.approx(1 / 13)

    def test_ties_rank_by_key_and_weights_scale_a_leg(self) -> None:
        fused = RRF(k=1, weights={"vector": 2.0, "lexical": 1.0}).fuse({"vector": {"b": 1.0, "a": 1.0}})
        assert fused == {"a": pytest.approx(2 / 2), "b": pytest.approx(2 / 3)}
        assert RRF().k == 10 and RRF().weights == dict.fromkeys(LEG_NAMES, 1.0)

    def test_identity_and_refusals(self) -> None:
        assert RRF() == RRF(10) and hash(RRF(10)) == hash(RRF()) and RRF(5) != RRF()
        assert repr(RRF(5)) == "RRF(k=5, weights={'vector': 1.0, 'lexical': 1.0})"
        with pytest.raises(ValueError, match="at least 1"):
            RRF(0)
        with pytest.raises(ValueError, match="unknown legs"):
            RRF(weights={"graph": 1.0})
        with pytest.raises(ValueError, match="positive"):
            RRF(weights={"vector": -1.0})


class TestRanker:
    def test_defaults_identity_and_repr(self) -> None:
        ranker = Ranker()
        assert ranker.fusion == Convex() and ranker.aggregate == MaxP(3)
        assert ranker == Ranker(fusion=Convex(), aggregate=MaxP()) and hash(ranker) == hash(Ranker())
        assert Ranker(fusion=RRF()) != ranker
        assert repr(MaxP()) == "MaxP(chunks_per_entry=3)"
        expected = (
            "Ranker(signals=(), fusion=Convex({'vector': 0.5, 'lexical': 0.5}), aggregate=MaxP(chunks_per_entry=3))"
        )
        assert repr(ranker) == expected

    def test_signals_are_part_of_identity_and_names_are_unique(self) -> None:
        one = Ranker(signals=(Signal("centrality"),))
        assert one != Ranker() and one == Ranker(signals=(Signal("centrality"),)) and hash(one) == hash(one)
        with pytest.raises(ValueError, match="repeat"):
            Ranker(signals=(Signal("centrality"), Signal("centrality", weight=0.3)))


class TestSignal:
    def test_defaults_and_the_options_fingerprint(self) -> None:
        signal = Signal("centrality")
        assert (signal.measure, signal.smoothing, signal.transform, signal.weight) == (InDegree(), 0.2, Linear(), 0.15)
        # The fingerprint follows what is stored: the measure and the smoothing, never the query-time shaping.
        assert signal.options_hash() == Signal("centrality", transform=Log1p(), weight=0.4).options_hash()
        assert signal.options_hash() != Signal("centrality", smoothing=0.0).options_hash()
        assert signal.options_hash() != Signal("centrality", measure=PageRank()).options_hash()

    def test_the_factor_is_one_plus_weight_times_the_transform(self) -> None:
        assert Signal("s", weight=0.5).factor(1.0) == 1.5
        assert Signal("s", weight=0.5, transform=Log1p()).factor(0.0) == 1.0
        assert Signal("s", weight=1.0, transform=Saturation(pivot=1.0)).factor(1.0) == 1.5
        assert Signal("s", weight=1.0, transform=Sigmoid(pivot=0.5, exponent=2.0)).factor(0.5) == 1.5

    @pytest.mark.parametrize(
        ("kwargs", "match"),
        [
            ({"name": "Centrality"}, "lowercase"),
            ({"name": "x" * 33}, "lowercase"),
            ({"name": "s", "smoothing": 0.5}, "smoothing"),
            ({"name": "s", "smoothing": -0.1}, "smoothing"),
            ({"name": "s", "weight": 0.0}, "weight"),
            ({"name": "s", "weight": 1.5}, "weight"),
        ],
    )
    def test_refusals(self, kwargs: dict[str, object], match: str) -> None:
        with pytest.raises(ValueError, match=match):
            Signal(**cast("Any", kwargs))

    def test_measures_validate_and_name_their_kernel(self) -> None:
        assert InDegree().kernel_args() == ("in_degree", 0.0, 0.0, 1)
        assert PageRank().kernel_args() == ("pagerank", 0.85, 0.0, 20)
        assert Katz(alpha=0.2, iterations=5).kernel_args() == ("katz", 0.0, 0.2, 5)
        assert PathShape().sign == -1
        for bad in (lambda: PageRank(damping=1.0), lambda: PageRank(iterations=0), lambda: Katz(alpha=0.0)):
            with pytest.raises(ValueError):
                bad()
        with pytest.raises(ValueError, match="iterations"):
            Katz(iterations=0)
        with pytest.raises(ValueError, match="sign"):
            PathShape(sign=0)

    def test_transforms_validate(self) -> None:
        with pytest.raises(ValueError, match="pivot"):
            Saturation(pivot=0.0)
        with pytest.raises(ValueError, match="pivot"):
            Sigmoid(exponent=0.0)
        assert Linear().apply(0.25) == 0.25

    def test_maxp_refuses_zero_chunks(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            MaxP(0)
        assert MaxP(2) != MaxP(3) and hash(MaxP(2)) == hash(MaxP(2))
