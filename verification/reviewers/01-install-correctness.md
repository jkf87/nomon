# Reviewer 1: Install Correctness

**Dimension:** Install accuracy and robustness (70% auto-test + 30% qualitative).

**Auto-Test:** Run verification/auto/run_install_test.sh. Exit 0 = pass, ≠0 = fail.

**Qualitative:** Idempotency, rollback safety, user content protection, error messages.

**Score:** 90-100 (all pass) | 75-89 (1-2 gaps) | 50-74 (major gaps) | <50 (critical)
