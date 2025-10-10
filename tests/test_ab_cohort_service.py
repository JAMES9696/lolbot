from src.core.services.ab_testing import CohortAssignmentService


def test_cohort_assignment_is_deterministic():
    svc = CohortAssignmentService(variant_a_weight=0.5, variant_b_weight=0.5, seed="fixed")
    uid = "123456789012345678"
    first = svc.assign_variant(uid)
    for _ in range(10):
        assert svc.assign_variant(uid) == first


def test_cohort_assignment_distribution():
    svc = CohortAssignmentService(variant_a_weight=0.3, variant_b_weight=0.7, seed="fixed")
    # Simulate 1000 users
    a_count = 0
    b_count = 0
    for i in range(1000):
        v = svc.assign_variant(f"user-{i}")
        if v == "A":
            a_count += 1
        else:
            b_count += 1
    a_ratio = a_count / (a_count + b_count)
    assert 0.25 <= a_ratio <= 0.35  # ±5% tolerance around 0.30
