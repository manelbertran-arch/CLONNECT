"""
ECHO Engine Testing & Validation Framework.

Modules:
    generate_test_set  - Extract real conversations from DB into test sets
    evaluator          - 6-dimension CloneScore evaluator (auto + LLM-judge)
    ab_comparison      - Blind A/B test: clone vs real creator
    regression_test    - Pre-deploy regression with baseline comparison
    stress_test        - Concurrent load testing with latency percentiles
    stefano_validation - Generate HTML exam for creator subjective review
    dashboard_data     - Export metrics for frontend dashboard
    run_validation     - Master script orchestrating all tests
"""
