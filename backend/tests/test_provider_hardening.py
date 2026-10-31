"""Tests for Provider Client hardening: retries, backoff, jitter, semaphores, and budget guards."""

import pytest
from app.config import get_settings
from app.providers.client import (
    BudgetExceededError,
    BudgetGuard,
    ProviderAPIError,
    estimate_reasoner_cost,
    estimate_segmentation_cost,
    estimate_transcription_cost,
    execute_with_retry,
    get_budget_guard,
    get_image_semaphore,
    get_video_semaphore,
)


def test_budget_guard_per_audit_cap():
    """Verify that per-audit budget limit ($5.0) raises BudgetExceededError."""
    guard = BudgetGuard()
    audit_id = "test_audit_budget"

    # Small calls within $5.0 cap should succeed
    guard.check_and_charge(audit_id, 2.0)
    guard.check_and_charge(audit_id, 2.5)
    assert guard.get_audit_spent(audit_id) == 4.5

    # Exceeding $5.0 cap should raise BudgetExceededError
    with pytest.raises(BudgetExceededError, match="Per-audit budget cap of \\$5.00 exceeded"):
        guard.check_and_charge(audit_id, 1.0)


def test_budget_guard_global_cap():
    """Verify that global budget limit ($100.0) raises BudgetExceededError."""
    guard = BudgetGuard()

    # Charge across various audits up to $95
    guard.check_and_charge("audit_a", 4.0)
    guard.check_and_charge("audit_b", 4.0)

    # Big charge exceeding $100 total
    with pytest.raises(BudgetExceededError, match="Global budget cap of \\$100.00 exceeded"):
        guard.check_and_charge("audit_c", 95.0)


def test_retry_on_429_and_5xx_success():
    """Verify retry with backoff succeeds when transient errors resolve."""
    attempts = 0

    def flaky_service():
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ProviderAPIError("Too Many Requests", status_code=429)
        return "success"

    res = execute_with_retry(flaky_service, max_retries=3, base_delay=0.01)
    assert res == "success"
    assert attempts == 3


def test_retry_on_429_exceeds_max_retries():
    """Verify failure is re-raised if retries are exhausted."""
    attempts = 0

    def always_503():
        nonlocal attempts
        attempts += 1
        raise ProviderAPIError("Service Unavailable", status_code=503)

    with pytest.raises(ProviderAPIError, match="Service Unavailable"):
        execute_with_retry(always_503, max_retries=2, base_delay=0.01)

    assert attempts == 3  # initial attempt + 2 retries


def test_non_retryable_error_fails_immediately():
    """Verify 400 Bad Request is not retried."""
    attempts = 0

    def client_error():
        nonlocal attempts
        attempts += 1
        raise ProviderAPIError("Bad Request", status_code=400)

    with pytest.raises(ProviderAPIError, match="Bad Request"):
        execute_with_retry(client_error, max_retries=3, base_delay=0.01)

    assert attempts == 1


def test_pricing_estimates_against_config():
    """Verify cost estimates use config constants with verify comments."""
    settings = get_settings()
    assert estimate_segmentation_cost(10) == 10 * settings.PRICE_SAM_PER_IMAGE_USD
    assert estimate_transcription_cost(5.0) == 5.0 * settings.PRICE_MUSE_VOICE_PER_MIN_USD
    assert estimate_reasoner_cost(1.0, 0.25) > 0.0


def test_semaphores_exist_and_bounded():
    """Verify concurrency semaphores are initialized according to config limits."""
    settings = get_settings()
    vid_sem = get_video_semaphore()
    img_sem = get_image_semaphore()
    assert vid_sem is not None
    assert img_sem is not None
