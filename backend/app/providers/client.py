"""Hardened provider client: timeout, retry with backoff and jitter, semaphores, and budget guard."""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Callable, TypeVar

from app.config import get_settings

logger = logging.getLogger("auditlens.providers.client")

T = TypeVar("T")


class BudgetExceededError(RuntimeError):
    """Raised when an operation would exceed per-audit or global budget caps."""
    pass


class ProviderAPIError(RuntimeError):
    """Base error for provider HTTP / service calls."""
    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.status_code = status_code


class BudgetGuard:
    """
    Per-audit and global budget guard.
    Stops provider requests when per-audit cap ($5) or global cap ($100) is exceeded.
    Estimates cost from config.py constants (verify at dev.meta.ai pricing).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._audit_spending: dict[str, float] = {}
        self._global_spending: float = 0.0

    def check_and_charge(self, audit_id: str | None, estimated_cost_usd: float) -> None:
        """
        Verify that adding estimated_cost_usd does not exceed per-audit ($5) or global ($100) cap.
        Raises BudgetExceededError if capped.
        """
        settings = get_settings()
        cost = max(0.0, float(estimated_cost_usd))

        with self._lock:
            # 1. Check Global Cap ($100 default)
            projected_global = self._global_spending + cost
            if projected_global > settings.MAX_GLOBAL_BUDGET_USD:
                raise BudgetExceededError(
                    f"Global budget cap of ${settings.MAX_GLOBAL_BUDGET_USD:.2f} exceeded: "
                    f"current total ${self._global_spending:.4f}, attempted call costs ${cost:.4f}. "
                    "Halting provider calls to prevent unexpected billing."
                )

            # 2. Check Per-Audit Cap ($5 default)
            if audit_id:
                audit_spent = self._audit_spending.get(audit_id, 0.0)
                projected_audit = audit_spent + cost
                if projected_audit > settings.MAX_BUDGET_PER_AUDIT_USD:
                    raise BudgetExceededError(
                        f"Per-audit budget cap of ${settings.MAX_BUDGET_PER_AUDIT_USD:.2f} exceeded for audit '{audit_id}': "
                        f"current audit cost ${audit_spent:.4f}, attempted call costs ${cost:.4f}. "
                        "Halting provider calls to prevent unexpected billing."
                    )
                self._audit_spending[audit_id] = projected_audit

            self._global_spending = projected_global
            logger.debug(
                "BudgetGuard charged $%.4f (audit_id=%s, audit_total=$%.4f, global_total=$%.4f)",
                cost,
                audit_id,
                self._audit_spending.get(audit_id or "", 0.0),
                self._global_spending,
            )

    def get_audit_spent(self, audit_id: str) -> float:
        with self._lock:
            return self._audit_spending.get(audit_id, 0.0)

    def get_global_spent(self) -> float:
        with self._lock:
            return self._global_spending

    def reset(self) -> None:
        """Reset budget tracking counters (for testing)."""
        with self._lock:
            self._audit_spending.clear()
            self._global_spending = 0.0


# Singleton BudgetGuard
_budget_guard = BudgetGuard()


def get_budget_guard() -> BudgetGuard:
    return _budget_guard


# Concurrency Semaphores (default 1 for video, 4 for images)
_video_semaphore: threading.Semaphore | None = None
_image_semaphore: threading.Semaphore | None = None
_sem_lock = threading.Lock()


def get_video_semaphore() -> threading.Semaphore:
    global _video_semaphore
    with _sem_lock:
        if _video_semaphore is None:
            settings = get_settings()
            _video_semaphore = threading.Semaphore(settings.VIDEO_CONCURRENCY_LIMIT)
        return _video_semaphore


def get_image_semaphore() -> threading.Semaphore:
    global _image_semaphore
    with _sem_lock:
        if _image_semaphore is None:
            settings = get_settings()
            _image_semaphore = threading.Semaphore(settings.IMAGE_CONCURRENCY_LIMIT)
        return _image_semaphore


def estimate_segmentation_cost(num_images: int) -> float:
    """Estimate SAM 3.1 cost based on image count (verify at dev.meta.ai pricing)."""
    settings = get_settings()
    return num_images * settings.PRICE_SAM_PER_IMAGE_USD


def estimate_reasoner_cost(input_tokens_k: float = 1.0, output_tokens_k: float = 0.25) -> float:
    """Estimate Muse Spark cost based on tokens (verify at dev.meta.ai pricing)."""
    settings = get_settings()
    return (
        input_tokens_k * settings.PRICE_MUSE_SPARK_INPUT_PER_1K_USD
        + output_tokens_k * settings.PRICE_MUSE_SPARK_OUTPUT_PER_1K_USD
    )


def estimate_transcription_cost(duration_minutes: float) -> float:
    """Estimate Muse Voice Transcribe cost based on audio duration (verify at dev.meta.ai pricing)."""
    settings = get_settings()
    return duration_minutes * settings.PRICE_MUSE_VOICE_PER_MIN_USD


def is_retryable_error(exc: Exception) -> bool:
    """Determine if exception is a 429 (rate limit) or 5xx (server error)."""
    # Check status_code attribute
    status = getattr(exc, "status_code", None)
    if status is None and hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        status = exc.response.status_code

    if status is not None:
        return status == 429 or (500 <= status <= 599)

    # Check error message for HTTP status codes
    msg = str(exc).lower()
    if "429" in msg or "rate limit" in msg or "500" in msg or "502" in msg or "503" in msg or "504" in msg:
        return True

    return False


def execute_with_retry(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int | None = None,
    base_delay: float = 0.1,
    is_video: bool = False,
    audit_id: str | None = None,
    estimated_cost: float = 0.0,
    **kwargs: Any,
) -> T:
    """
    Execute provider function with:
    1. Budget guard pre-check
    2. Concurrency semaphore acquisition (video vs image)
    3. Exponential backoff and jitter retry on 429 and 5xx
    """
    settings = get_settings()
    retries = max_retries if max_retries is not None else settings.PROVIDER_MAX_RETRIES

    # 1. Verify and charge budget before network call
    if estimated_cost > 0:
        get_budget_guard().check_and_charge(audit_id, estimated_cost)

    # 2. Acquire appropriate concurrency semaphore
    semaphore = get_video_semaphore() if is_video else get_image_semaphore()

    with semaphore:
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < retries and is_retryable_error(exc):
                    # Exponential backoff with jitter
                    jitter = random.uniform(0.01, 0.05 * (2 ** attempt))
                    delay = (base_delay * (2 ** attempt)) + jitter
                    logger.warning(
                        "Provider call failed with retryable error (attempt %d/%d): %s. Retrying in %.3fs...",
                        attempt + 1,
                        retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    raise exc

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("execute_with_retry: unknown failure")
