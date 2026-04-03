#!/usr/bin/env python3
"""
CCEE Script 6: Build Evaluator

CLI orchestrator that builds the complete evaluator profile for a creator:
  1. Style profile (A1-A9 metrics)
  2. Strategy map (per input type)
  3. Adaptation profile (per trust segment)

Usage:
    railway run python3 scripts/build_evaluator.py --creator iris_bertran
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.evaluation.style_profile_builder import StyleProfileBuilder, save_profile
from core.evaluation.strategy_map_builder import StrategyMapBuilder, save_strategy_map
from core.evaluation.adaptation_profiler import AdaptationProfiler, save_adaptation_profile


def main():
    parser = argparse.ArgumentParser(
        description="Build CCEE evaluator profile for a creator"
    )
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument(
        "--output-dir", default="evaluation_profiles",
        help="Output directory (default: evaluation_profiles)"
    )
    parser.add_argument(
        "--skip-adaptation", action="store_true",
        help="Skip adaptation profiling (faster, for testing)"
    )
    args = parser.parse_args()

    creator = args.creator
    output_dir = args.output_dir

    print(f"{'='*60}")
    print(f" CCEE Evaluator Builder — {creator}")
    print(f"{'='*60}\n")

    # Step 1: Style Profile
    print("[1/3] Building style profile...")
    t0 = time.time()
    style_builder = StyleProfileBuilder()
    style_profile = style_builder.build(creator)
    style_path = save_profile(style_profile, creator, output_dir)
    t1 = time.time()
    print(f"  -> {style_path} ({t1-t0:.1f}s)")
    print(f"  -> {style_profile['total_messages']} messages processed")
    print(f"  -> {style_profile['total_pairs']} pairs extracted")
    print(f"  -> Languages: {style_profile['A6_language_ratio']['ratios']}")
    print(f"  -> Catchphrases: {len(style_profile['A9_catchphrases']['catchphrases'])}")

    # Step 2: Strategy Map
    print("\n[2/3] Building strategy map...")
    t0 = time.time()
    strategy_builder = StrategyMapBuilder()
    strategy_map = strategy_builder.build(creator)
    strategy_path = save_strategy_map(strategy_map, creator, output_dir)
    t1 = time.time()
    print(f"  -> {strategy_path} ({t1-t0:.1f}s)")
    print(f"  -> {strategy_map['total_sessions']} sessions")
    print(f"  -> {strategy_map['total_pairs']} pairs")
    print(f"  -> Global distribution: {strategy_map['global_strategy_distribution']}")

    # Step 3: Adaptation Profile
    if args.skip_adaptation:
        print("\n[3/3] Skipping adaptation profile (--skip-adaptation)")
        adapt_path = None
    else:
        print("\n[3/3] Building adaptation profile...")
        t0 = time.time()
        adapt_builder = AdaptationProfiler()
        adapt_profile = adapt_builder.build(creator)
        adapt_path = save_adaptation_profile(adapt_profile, creator, output_dir)
        t1 = time.time()
        print(f"  -> {adapt_path} ({t1-t0:.1f}s)")
        print(f"  -> Segments: {adapt_profile['segment_counts']}")
        print(f"  -> Adaptation score: {adapt_profile['adaptation']['adaptation_score']}")

    # Summary
    print(f"\n{'='*60}")
    print(f" Evaluator built for {creator}")
    print(f"  Style: {style_path}")
    print(f"  Strategy: {strategy_path}")
    print(f"  Adaptation: {adapt_path or 'SKIPPED'}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
