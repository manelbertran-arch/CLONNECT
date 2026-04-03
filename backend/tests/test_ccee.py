"""
CCEE Test Suite — 20+ tests covering all evaluation modules.

Tests use synthetic data (no DB required). Run with:
    python3 -m pytest tests/test_ccee.py -x -q
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.evaluation.style_profile_builder import (
    EMOJI_RE,
    _percentiles,
    _threshold,
    classify_context,
)
from core.evaluation.strategy_map_builder import classify_strategy
from core.evaluation.adaptation_profiler import _trust_segment
from core.evaluation.ccee_scorer import (
    CCEEScorer,
    DEFAULT_WEIGHTS,
    _detect_bot_reveal,
    _detect_hallucination,
    _echo_rate,
    _jsd,
    _within_range,
    score_j1_memory_recall,
    score_j2_multiturn_consistency,
    score_s1_style_fidelity,
    score_s2_response_quality,
    score_s3_strategic_alignment,
    score_s4_adaptation,
)
from core.evaluation.calibrator import CCEECalibrator, spearman_rho


# =====================================================================
# Fixtures: synthetic profiles
# =====================================================================

@pytest.fixture
def sample_style_profile():
    return {
        "creator_id": "test_creator",
        "total_messages": 100,
        "total_pairs": 80,
        "A1_length": {
            "mean": 45.0, "median": 40.0, "std": 15.0,
            "P10": 15.0, "P25": 25.0, "P75": 60.0, "P90": 80.0,
            "threshold": [15.0, 80.0], "count": 100,
        },
        "A2_emoji": {
            "global_rate": 0.6,
            "emoji_count_stats": {"mean": 1.2},
            "per_context": {
                "GREETING": {"rate": 0.8, "count": 20},
                "HEALTH": {"rate": 0.1, "count": 15},
                "LAUGH": {"rate": 0.9, "count": 10},
                "OTHER": {"rate": 0.5, "count": 35},
            },
            "threshold_global": [0.0, 1.0],
        },
        "A3_exclamations": {"rate": 0.4, "threshold": [0.0, 1.0]},
        "A4_questions": {"rate": 0.3, "threshold": [0.0, 1.0]},
        "A5_vocabulary": {
            "top_50": [
                {"word": "genial", "score": 2.5},
                {"word": "increíble", "score": 2.1},
                {"word": "perfecte", "score": 1.8},
            ],
            "method": "tfidf",
        },
        "A6_language_ratio": {"ratios": {"ca": 0.6, "es": 0.3, "en": 0.1}},
        "A7_fragmentation": {"mean": 1.5, "threshold": [1.0, 3.0]},
        "A8_formality": {
            "formal_rate": 0.02, "informal_rate": 0.3,
            "abbreviation_rate": 0.1, "formality_score": 0.06,
        },
        "A9_catchphrases": {
            "catchphrases": [
                {"phrase": "qué genial", "count": 12},
                {"phrase": "molt bé", "count": 8},
            ]
        },
    }


@pytest.fixture
def sample_strategy_map():
    return {
        "strategy_map": {
            "GREETING": {
                "distribution": {"MIRROR": 0.5, "ASK": 0.3, "VALIDATE": 0.2},
                "count": 20, "dominant": "MIRROR",
            },
            "HEALTH": {
                "distribution": {"VALIDATE": 0.6, "ASK": 0.3, "INFORM": 0.1},
                "count": 15, "dominant": "VALIDATE",
            },
            "QUESTION_SERVICE": {
                "distribution": {"INFORM": 0.7, "ASK": 0.2, "REDIRECT": 0.1},
                "count": 25, "dominant": "INFORM",
            },
            "EMOTIONAL": {
                "distribution": {"VALIDATE": 0.7, "ASK": 0.2, "MIRROR": 0.1},
                "count": 10, "dominant": "VALIDATE",
            },
            "LAUGH": {
                "distribution": {"MIRROR": 0.8, "VALIDATE": 0.2},
                "count": 10, "dominant": "MIRROR",
            },
            "OTHER": {
                "distribution": {"ASK": 0.4, "VALIDATE": 0.3, "INFORM": 0.3},
                "count": 20, "dominant": "ASK",
            },
        },
        "global_strategy_distribution": {
            "MIRROR": 0.25, "ASK": 0.25, "VALIDATE": 0.25,
            "INFORM": 0.15, "REDIRECT": 0.05, "IGNORE": 0.05,
        },
    }


@pytest.fixture
def sample_adaptation_profile():
    return {
        "segments": {
            "UNKNOWN": {
                "message_count": 500,
                "A1_length": {
                    "mean": 20.0, "median": 18.0, "std": 10.0,
                    "P10": 5.0, "P25": 10.0, "P75": 30.0, "P90": 40.0, "count": 500,
                },
                "A2_emoji_rate": 0.2,
                "A3_exclamation_rate": 0.3,
                "A4_question_rate": 0.5,
                "A5_vocab_diversity": 0.25,
            },
            "KNOWN": {
                "message_count": 200,
                "A1_length": {
                    "mean": 35.0, "median": 30.0, "std": 15.0,
                    "P10": 10.0, "P25": 20.0, "P75": 50.0, "P90": 65.0, "count": 200,
                },
                "A2_emoji_rate": 0.5,
                "A3_exclamation_rate": 0.32,
                "A4_question_rate": 0.3,
                "A5_vocab_diversity": 0.40,
            },
            "CLOSE": {
                "message_count": 100,
                "A1_length": {
                    "mean": 55.0, "median": 50.0, "std": 20.0,
                    "P10": 20.0, "P25": 35.0, "P75": 70.0, "P90": 90.0, "count": 100,
                },
                "A2_emoji_rate": 0.8,
                "A3_exclamation_rate": 0.31,
                "A4_question_rate": 0.1,
                "A5_vocab_diversity": 0.45,
            },
        },
        "adaptation": {
            "adaptation_score": 60.0,
            "valid_segments": 3,
            "directions": {
                "length_mean": {
                    "direction": "increases_with_trust", "magnitude": 0.3,
                    "values_by_segment": {"UNKNOWN": 20, "KNOWN": 35, "CLOSE": 55},
                },
                "emoji_rate": {
                    "direction": "increases_with_trust", "magnitude": 0.4,
                    "values_by_segment": {"UNKNOWN": 0.2, "KNOWN": 0.5, "CLOSE": 0.8},
                },
                "exclamation_rate": {
                    "direction": "neutral", "magnitude": 0.05,
                    "values_by_segment": {"UNKNOWN": 0.3, "KNOWN": 0.32, "CLOSE": 0.31},
                },
                "question_rate": {
                    "direction": "decreases_with_trust", "magnitude": 0.2,
                    "values_by_segment": {"UNKNOWN": 0.5, "KNOWN": 0.3, "CLOSE": 0.1},
                },
                "vocab_diversity": {
                    "direction": "neutral", "magnitude": 0.02,
                },
            },
        },
    }


# =====================================================================
# 1-6: StyleProfileBuilder tests
# =====================================================================

class TestContextClassifier:
    """Tests 1-3: Context classification."""

    def test_emoji_only(self):
        assert classify_context("😂🔥❤️") == "EMOJI_ONLY"
        assert classify_context("👍") == "EMOJI_ONLY"

    def test_greeting_multilingual(self):
        assert classify_context("Hola, cómo estás?") == "GREETING"
        assert classify_context("Bon dia!") == "GREETING"
        assert classify_context("Hello there") == "GREETING"
        assert classify_context("Ciao!") == "GREETING"

    def test_question_service(self):
        assert classify_context("Cuánto cuesta la clase?") == "QUESTION_SERVICE"
        assert classify_context("What's the price?") == "QUESTION_SERVICE"
        assert classify_context("Quin és el preu?") == "QUESTION_SERVICE"

    def test_emotional(self):
        assert classify_context("Estoy muy triste hoy") == "EMOTIONAL"
        assert classify_context("I'm so frustrated") == "EMOTIONAL"

    def test_health(self):
        assert classify_context("Estoy en el hospital") == "HEALTH"
        assert classify_context("Me duele mucho la espalda") == "HEALTH"

    def test_laugh(self):
        assert classify_context("jajajaja") == "LAUGH"
        assert classify_context("😂😂😂 me muero") == "LAUGH"
        assert classify_context("lol that's funny") == "LAUGH"

    def test_media(self):
        assert classify_context("[audio] voice message") == "MEDIA"
        assert classify_context("[image] photo") == "MEDIA"

    def test_other_fallback(self):
        assert classify_context("Me gustan los gatos") == "OTHER"
        assert classify_context("") == "OTHER"


class TestStyleMetrics:
    """Tests 4-6: Metric computation helpers."""

    def test_a1_percentiles(self):
        values = list(range(1, 101))
        stats = _percentiles(values)
        assert abs(stats["mean"] - 50.5) < 0.01
        assert abs(stats["median"] - 50.5) < 0.01
        assert stats["P10"] == pytest.approx(10.9, abs=0.5)
        assert stats["P90"] == pytest.approx(90.1, abs=0.5)

    def test_a9_catchphrases_detection(self):
        """Repeated n-grams should be detected."""
        from core.evaluation.style_profile_builder import StyleProfileBuilder
        builder = StyleProfileBuilder()
        # Use non-stopword words with 3+ chars
        messages = ["genial perfecte increíble fantàstic"] * 10 + ["altre cosa diferent"] * 3
        result = builder._compute_a9(messages)
        phrases = [cp["phrase"] for cp in result["catchphrases"]]
        # "genial perfecte" repeated 10 times → should appear
        assert any("genial" in p for p in phrases)
        assert len(phrases) >= 1

    def test_a6_language_ratio_counts(self):
        """Language detection should count correctly."""
        from core.evaluation.style_profile_builder import StyleProfileBuilder
        builder = StyleProfileBuilder()
        messages = [
            "Hola, ¿cómo estás?",  # ES
            "Bon dia, com estàs?",  # CA
            "Hello, how are you?",  # EN
        ]
        result = builder._compute_a6(messages)
        assert result["total_detected"] == 3
        assert len(result["ratios"]) >= 1


# =====================================================================
# 7-10: StrategyMapBuilder tests
# =====================================================================

class TestStrategyClassifier:
    """Tests 7-10: Strategy classification."""

    def test_mirror_detection(self):
        """Short + emoji = MIRROR."""
        assert classify_strategy("jajaja", "😂😂") == "MIRROR"
        assert classify_strategy("hola!", "hola! 👋") == "MIRROR"

    def test_ask_detection(self):
        """Response with question mark = ASK."""
        assert classify_strategy("Estoy bien", "Qué tal el día?") == "ASK"

    def test_inform_detection(self):
        """Response with factual data = INFORM."""
        result = classify_strategy(
            "Cuánto cuesta?",
            "El precio es de 97€ y puedes reservar en https://example.com"
        )
        assert result == "INFORM"

    def test_validate_detection(self):
        """Response with empathetic markers = VALIDATE."""
        result = classify_strategy(
            "Estoy muy triste",
            "Ostres, ho sento molt. Entenc com et sents."
        )
        assert result == "VALIDATE"


# =====================================================================
# 11: AdaptationProfiler tests
# =====================================================================

class TestAdaptationProfiler:
    """Tests 11: Trust segmentation."""

    def test_trust_segmentation(self):
        assert _trust_segment(0.1) == "UNKNOWN"
        assert _trust_segment(0.5) == "KNOWN"
        assert _trust_segment(0.8) == "CLOSE"
        assert _trust_segment(0.95) == "INTIMATE"

    def test_adaptation_direction(self):
        """Synthetic segments with clear direction should be detected."""
        from core.evaluation.adaptation_profiler import AdaptationProfiler
        profiler = AdaptationProfiler()

        segments = {
            "UNKNOWN": {
                "message_count": 30,
                "A1_length": {"mean": 15.0},
                "A2_emoji_rate": 0.1,
                "A3_exclamation_rate": 0.2,
                "A4_question_rate": 0.5,
                "A5_vocab_diversity": 0.8,
            },
            "KNOWN": {
                "message_count": 30,
                "A1_length": {"mean": 40.0},
                "A2_emoji_rate": 0.5,
                "A3_exclamation_rate": 0.3,
                "A4_question_rate": 0.3,
                "A5_vocab_diversity": 0.7,
            },
            "CLOSE": {
                "message_count": 20,
                "A1_length": {"mean": 65.0},
                "A2_emoji_rate": 0.8,
                "A3_exclamation_rate": 0.35,
                "A4_question_rate": 0.1,
                "A5_vocab_diversity": 0.6,
            },
        }

        result = profiler._compute_adaptation_direction(segments)
        assert result["adaptation_score"] > 50
        # Length should increase with trust
        assert result["directions"]["length_mean"]["direction"] == "increases_with_trust"


# =====================================================================
# 12-16: CCEEScorer tests
# =====================================================================

class TestCCEEScorer:
    """Tests 12-16: Scoring engine."""

    def test_s1_within_range_perfect(self, sample_style_profile):
        """Response within [P10, P90] range should score higher than outside."""
        # 40 chars is within [15, 80] threshold
        responses = ["x" * 40 + " genial! 😊"] * 5
        result = score_s1_style_fidelity(responses, sample_style_profile)
        assert result["score"] > 0
        assert result["detail"]["A1_length"] > 50  # length within range scores well

    def test_s1_outside_range_penalty(self, sample_style_profile):
        """Response far outside range should score lower."""
        # 200 chars far outside [15, 80]
        long_responses = ["x" * 200] * 5
        short_responses = ["x" * 40] * 5
        long_result = score_s1_style_fidelity(long_responses, sample_style_profile)
        short_result = score_s1_style_fidelity(short_responses, sample_style_profile)
        assert short_result["score"] > long_result["score"]

    def test_s2_identical_high_score(self):
        """Identical bot response and ground truth should score high."""
        test_cases = [
            {"user_input": "Hola!", "ground_truth": "Hola! Com estàs? 😊"},
        ] * 5
        bot_responses = ["Hola! Com estàs? 😊"] * 5
        result = score_s2_response_quality(test_cases, bot_responses)
        assert result["score"] > 60

    def test_s2_echo_penalty(self):
        """Bot that copies user input should get G4 penalty."""
        test_cases = [
            {"user_input": "Hola cómo estás hoy en esta mañana soleada",
             "ground_truth": "Muy bien! Hoy es un gran día"},
        ]
        # Bot echoes the user input
        bot_responses = ["Hola cómo estás hoy en esta mañana soleada"]
        result = score_s2_response_quality(test_cases, bot_responses)
        assert result["detail"]["g4_echo_mean"] > 0

    def test_s2_bot_reveal_penalty(self):
        """Bot revealing it's AI should be penalized."""
        assert _detect_bot_reveal("Soy un asistente de inteligencia artificial")
        assert _detect_bot_reveal("I'm a language model")
        assert not _detect_bot_reveal("Hola, què tal?")

    def test_s2_hallucination_detection(self):
        """Hallucination indicators should be detected."""
        assert _detect_hallucination("Según mi base de datos, el precio es...")
        assert not _detect_hallucination("El precio es 97€")

    def test_s3_matching_strategy_high(self, sample_strategy_map):
        """Bot matching creator's dominant strategy should score high."""
        # Creator uses MIRROR for LAUGH (0.8)
        test_cases = [
            {"user_input": "jajajaja qué bueno"},
        ]
        # Bot mirrors with short emoji response
        bot_responses = ["😂😂"]
        result = score_s3_strategic_alignment(
            test_cases, bot_responses, sample_strategy_map
        )
        assert result["score"] >= 80

    def test_s3_health_context_strategy_mismatch(self, sample_strategy_map):
        """Test #12: 'compa 😂' in HEALTH context → S3 low (strategy mismatch).

        Creator uses VALIDATE (0.6) or ASK (0.3) in HEALTH contexts.
        Bot responds with MIRROR (short + emoji) which is not in top 2.
        """
        test_cases = [
            {"user_input": "Estoy en el hospital, me van a operar"},
        ]
        # Bot responds casually with mirror strategy — inappropriate
        bot_responses = ["compa 😂"]
        result = score_s3_strategic_alignment(
            test_cases, bot_responses, sample_strategy_map
        )
        # MIRROR is not in HEALTH top 2 (VALIDATE, ASK)
        assert result["score"] < 50, (
            f"Expected low S3 for mirror response in HEALTH context, got {result['score']}"
        )

    def test_s4_proximity_not_fixed_50(self, sample_adaptation_profile):
        """S4 should use proximity scores when directional analysis is insufficient."""
        test_cases = [
            {"user_input": "Hola!", "trust_score": 0.1},   # UNKNOWN
            {"user_input": "Qué tal?", "trust_score": 0.5},  # KNOWN
            {"user_input": "Te quiero", "trust_score": 0.85},  # CLOSE
        ]
        bot_responses = [
            "Hola! 😊",            # short + emoji
            "Molt bé! Com va tot amb tu?",  # medium
            "Gràcies amor! Et trobo a faltar molt, espero veure't aviat 😘",  # long + emoji
        ]
        result = score_s4_adaptation(test_cases, bot_responses, sample_adaptation_profile)
        assert result["score"] != 50.0, (
            f"S4 should not be exactly 50.0, got {result}"
        )
        assert result["detail"].get("mode") in ("proximity_only", "blended")

    def test_s4_all_neutral_directions_still_varies(self):
        """S4 should vary even when all directions are neutral (real Iris scenario)."""
        profile = {
            "segments": {
                "UNKNOWN": {
                    "message_count": 8000,
                    "A1_length": {"P10": 7.0, "P90": 72.0},
                    "A2_emoji_rate": 0.34,
                    "A3_exclamation_rate": 0.03,
                    "A4_question_rate": 0.09,
                },
                "INTIMATE": {
                    "message_count": 10000,
                    "A1_length": {"P10": 7.0, "P90": 84.0},
                    "A2_emoji_rate": 0.26,
                    "A3_exclamation_rate": 0.025,
                    "A4_question_rate": 0.10,
                },
            },
            "adaptation": {
                "adaptation_score": 20.0,
                "valid_segments": 2,
                "directions": {
                    "length_mean": {"direction": "neutral", "magnitude": 0.05},
                    "emoji_rate": {"direction": "neutral", "magnitude": 0.05},
                    "exclamation_rate": {"direction": "neutral", "magnitude": 0.05},
                    "question_rate": {"direction": "neutral", "magnitude": 0.02},
                },
            },
        }
        test_cases = [
            {"user_input": "Hola", "trust_score": 0.1},
            {"user_input": "Qué tal?", "trust_score": 0.15},
            {"user_input": "Amor!", "trust_score": 0.95},
            {"user_input": "Te echo de menos", "trust_score": 0.92},
        ]
        bot_responses = ["Hola 😊", "Bé!", "T'estimo molt! 😘❤️", "Jo també, amor"]
        result = score_s4_adaptation(test_cases, bot_responses, profile)
        assert result["score"] != 50.0, (
            f"S4 should not be exactly 50.0 with neutral directions but real segment data, got {result}"
        )

    def test_composite_weight_sum(self, sample_style_profile, sample_strategy_map,
                                   sample_adaptation_profile):
        """Composite weights should sum to ~1.0 and score should be in [0, 100]."""
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 0.001
        assert "J" in DEFAULT_WEIGHTS

        scorer = CCEEScorer(
            sample_style_profile, sample_strategy_map, sample_adaptation_profile
        )
        test_cases = [
            {"user_input": "Hola!", "ground_truth": "Hola! 😊", "trust_score": 0.5},
        ] * 5
        bot_responses = ["Hola! 😊"] * 5
        result = scorer.score(test_cases, bot_responses)
        assert 0 <= result["composite"] <= 100
        assert "J1_memory_recall" in result
        assert "J2_multiturn_consistency" in result
        assert "J_cognitive_fidelity" in result


# =====================================================================
# 17-18: Calibrator tests
# =====================================================================

class TestCalibrator:
    """Tests 17-18: Weight calibration."""

    def test_spearman_perfect_correlation(self):
        """Identical rankings should give rho = 1.0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 20.0, 30.0, 40.0, 50.0]
        rho = spearman_rho(x, y)
        assert abs(rho - 1.0) < 0.001

    def test_spearman_inverse_correlation(self):
        """Inverse rankings should give rho = -1.0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [50.0, 40.0, 30.0, 20.0, 10.0]
        rho = spearman_rho(x, y)
        assert abs(rho + 1.0) < 0.001

    def test_calibrate_weights_sum_to_one(self):
        """Calibrated weights should sum to 1.0."""
        calibrator = CCEECalibrator()
        # Create synthetic evaluations with known correlation
        human_ratings = list(np.linspace(1, 5, 20))
        ccee_evals = []
        for rating in human_ratings:
            ccee_evals.append({
                "S1_style_fidelity": {"score": rating * 20},
                "S2_response_quality": {"score": 50 + np.random.randn() * 5},
                "S3_strategic_alignment": {"score": rating * 18},
                "S4_adaptation": {"score": 50 + np.random.randn() * 5},
            })

        result = calibrator.calibrate(human_ratings, ccee_evals)
        weights = result["calibrated_weights"]
        weight_sum = sum(weights.values())
        assert abs(weight_sum - 1.0) < 0.001
        # S1 and S3 should have higher weights (correlated with human)
        assert result["composite_rho"] > 0.5


# =====================================================================
# 19-20: Integration tests
# =====================================================================

class TestIntegration:
    """Tests 19-20: Full pipeline with synthetic data."""

    def test_full_scorer_pipeline(self, sample_style_profile, sample_strategy_map,
                                   sample_adaptation_profile):
        """Full scoring pipeline should complete without errors."""
        scorer = CCEEScorer(
            sample_style_profile, sample_strategy_map, sample_adaptation_profile
        )
        test_cases = [
            {"user_input": "Hola! Cómo va?", "ground_truth": "Molt bé! 😊",
             "trust_score": 0.1},
            {"user_input": "Cuánto cuesta?", "ground_truth": "97€ la sessió",
             "trust_score": 0.5},
            {"user_input": "jajaja", "ground_truth": "😂😂",
             "trust_score": 0.8},
            {"user_input": "Estoy triste", "ground_truth": "Ostres, ho sento molt",
             "trust_score": 0.3},
            {"user_input": "Me duele la espalda", "ground_truth": "Uf, espero que estiguis millor aviat",
             "trust_score": 0.6},
        ]
        bot_responses = [
            "Hola! Com estàs? 😊",
            "El preu és de 97€",
            "😂",
            "Vaya, lo siento mucho",
            "Espero que te recuperes pronto",
        ]
        result = scorer.score(test_cases, bot_responses)

        assert "S1_style_fidelity" in result
        assert "S2_response_quality" in result
        assert "S3_strategic_alignment" in result
        assert "S4_adaptation" in result
        assert "composite" in result
        assert 0 <= result["composite"] <= 100

    def test_baseline_comparison(self):
        """Wilcoxon + Cliff's delta should produce valid results."""
        scorer = CCEEScorer({}, {}, {})
        current = [70.0, 75.0, 72.0, 68.0, 80.0, 71.0, 73.0, 69.0, 74.0, 76.0]
        baseline = [60.0, 62.0, 58.0, 65.0, 63.0, 61.0, 59.0, 64.0, 62.0, 60.0]
        result = scorer.compare_to_baseline(current, baseline)
        assert result["verdict"] == "IMPROVES"
        assert result["p_value"] < 0.05
        assert result["cliffs_delta"] > 0

    def test_universality_english_creator(self, sample_style_profile):
        """Engine should work for an English-only creator profile."""
        en_profile = dict(sample_style_profile)
        en_profile["A6_language_ratio"] = {"ratios": {"en": 1.0}}
        en_profile["A5_vocabulary"]["top_50"] = [
            {"word": "amazing", "score": 2.0},
            {"word": "wonderful", "score": 1.5},
        ]
        en_profile["A9_catchphrases"]["catchphrases"] = [
            {"phrase": "oh my god", "count": 8},
        ]

        responses = ["That's amazing! How are you?"] * 3
        result = score_s1_style_fidelity(responses, en_profile)
        assert result["score"] > 0  # should not crash, should produce valid score


# =====================================================================
# CCEE v2: New metric tests
# =====================================================================

class TestCCEEv2Metrics:
    """Tests for D6 fix, A7, E2 JSD, F2 vocab, J1 memory, J2 consistency."""

    def test_d6_semsim_in_s2_detail(self):
        """S2 detail should include separate semsim (D6) and c4_relevance."""
        test_cases = [
            {"user_input": "Hola!", "ground_truth": "Hola! 😊"},
        ] * 5
        bot_responses = ["Hola! 😊"] * 5
        result = score_s2_response_quality(test_cases, bot_responses)
        assert "semsim_mean" in result["detail"]
        assert "c4_relevance_mean" in result["detail"]

    def test_a7_fragmentation_not_50(self, sample_style_profile):
        """A7 should not be hardcoded 50.0 for multi-line responses."""
        multiline = ["Primera línia\nSegona línia\nTercera"] * 5
        result = score_s1_style_fidelity(multiline, sample_style_profile)
        assert result["detail"]["A7_fragmentation"] != 50.0

    def test_e2_jsd_identical_distributions(self, sample_strategy_map):
        """JSD of identical distributions should give E2 = 100."""
        jsd = _jsd({"A": 0.5, "B": 0.5}, {"A": 0.5, "B": 0.5})
        assert jsd < 0.01

    def test_e2_jsd_different_distributions(self):
        """JSD of very different distributions should be > 0.5."""
        jsd = _jsd({"A": 1.0}, {"B": 1.0})
        assert jsd > 0.5

    def test_e2_in_s3_output(self, sample_strategy_map):
        """S3 should include E2 distribution match."""
        test_cases = [
            {"user_input": "jajajaja"},
            {"user_input": "Hola!"},
            {"user_input": "Cuánto cuesta?"},
        ]
        bot_responses = ["😂😂", "Hola! 😊", "97€ la sessió"]
        result = score_s3_strategic_alignment(
            test_cases, bot_responses, sample_strategy_map
        )
        assert "e2_distribution_match" in result["detail"]
        assert "bot_strategy_distribution" in result["detail"]

    def test_j1_memory_recall_no_multiturn(self):
        """J1 should return 50.0 when no multi-turn data."""
        test_cases = [{"user_input": "Hola", "username": "user1"}]
        bot_responses = ["Hola!"]
        result = score_j1_memory_recall(test_cases, bot_responses)
        assert result["score"] == 50.0

    def test_j1_memory_recall_with_facts(self):
        """J1 should score when multi-turn conversation has facts."""
        test_cases = [
            {"user_input": "Me llamo Maria y tengo cita a las 10:30", "username": "u1"},
            {"user_input": "Qué me dices?", "username": "u1"},
        ]
        # Bot references the name and time
        bot_responses = [
            "Hola Maria!",
            "Sí Maria, a las 10:30 te espero",
        ]
        result = score_j1_memory_recall(test_cases, bot_responses)
        assert result["score"] >= 0  # At least scores something

    def test_j2_consistency_basic(self, sample_style_profile):
        """J2 should return non-trivial score for sufficient responses."""
        bot_responses = [
            "Hola! Com estàs? 😊",
            "Molt bé! Gràcies",
            "Ja veig! 😂",
            "Perfecte, genial!",
            "Ah sí? Que bé!",
        ]
        result = score_j2_multiturn_consistency(bot_responses, sample_style_profile)
        assert result["score"] != 50.0
        assert 0 <= result["score"] <= 100

    def test_j2_insufficient_responses(self, sample_style_profile):
        """J2 should return 50.0 with < 5 responses."""
        result = score_j2_multiturn_consistency(["hi", "bye"], sample_style_profile)
        assert result["score"] == 50.0


# =====================================================================
# Bonus: Edge cases
# =====================================================================

class TestEdgeCases:
    """Additional edge case tests."""

    def test_empty_responses(self, sample_style_profile):
        result = score_s1_style_fidelity([], sample_style_profile)
        assert result["score"] == 0.0

    def test_single_response(self, sample_style_profile, sample_strategy_map):
        test_cases = [{"user_input": "hola", "ground_truth": "hola!"}]
        bot_responses = ["hola!"]
        result = score_s3_strategic_alignment(
            test_cases, bot_responses, sample_strategy_map
        )
        assert isinstance(result["score"], float)

    def test_within_range_exact_boundary(self):
        assert _within_range(15.0, 15.0, 80.0) == 100.0
        assert _within_range(80.0, 15.0, 80.0) == 100.0
