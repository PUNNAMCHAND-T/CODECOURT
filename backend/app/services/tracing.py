"""Langfuse and OpenTelemetry observability service for CodeCourt.

T6.3: Provides optional, crash-resilient tracing for pipeline workflows,
graph nodes, and LLM calls. If credentials are missing or Langfuse is offline,
operations degrade silently to a no-op implementation without interrupting
the PR review pipeline.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

from backend.app.core.config import Settings, get_settings
from backend.app.schemas.trace import PipelineTraceReport

logger = logging.getLogger(__name__)

try:
    from langfuse import Langfuse
except ImportError:  # pragma: no cover
    Langfuse = None  # type: ignore[misc,assignment]


class BaseTracer(ABC):
    """Abstract interface for pipeline and LLM execution tracing."""

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return True if active tracing is configured and enabled."""

    @abstractmethod
    def trace_pipeline(
        self,
        state: dict[str, Any],
        trace_report: PipelineTraceReport | None = None,
    ) -> str | None:
        """Record a completed review pipeline execution trace.

        Returns an observation/trace identifier string if emitted, else None.
        """

    @abstractmethod
    def trace_llm_generation(
        self,
        model: str,
        prompt: str,
        response: str,
        cost_usd: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Record an individual LLM prompt/completion generation span."""

    @abstractmethod
    def flush(self) -> None:
        """Flush queued trace events to the backend collector."""

    @abstractmethod
    def shutdown(self) -> None:
        """Flush and cleanly shut down tracing threads/exporters."""


class NoopTracer(BaseTracer):
    """Safe no-op tracer active when Langfuse is disabled or unconfigured."""

    def is_enabled(self) -> bool:
        return False

    def trace_pipeline(
        self,
        state: dict[str, Any],
        trace_report: PipelineTraceReport | None = None,
    ) -> str | None:
        return None

    def trace_llm_generation(
        self,
        model: str,
        prompt: str,
        response: str,
        cost_usd: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        return None

    def flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass


class LangfuseTracer(BaseTracer):
    """Crash-resilient Langfuse tracer emitting hierarchical pipeline observations."""

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
        client: Any = None,
    ) -> None:
        self.public_key = public_key
        self.secret_key = secret_key
        self.host = host
        self._client: Any = None
        self._active: bool = False

        if client is not None:
            self._client = client
            self._active = True
            return

        if not (self.public_key and self.secret_key and Langfuse is not None):
            logger.info("Langfuse credentials absent or SDK missing; tracing disabled.")
            return

        try:
            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
                debug=False,
            )
            self._active = True
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to initialize Langfuse client: %s; falling back to no-op", exc)
            self._active = False
            self._client = None

    def is_enabled(self) -> bool:
        return self._active and self._client is not None

    def trace_pipeline(
        self,
        state: dict[str, Any],
        trace_report: PipelineTraceReport | None = None,
    ) -> str | None:
        """Emit hierarchical pipeline trace with root chain and per-node spans."""
        if not self.is_enabled():
            return None

        try:
            owner = str(state.get("owner", ""))
            repo = str(state.get("repo", ""))
            pull_number = int(state.get("pull_number", 0) or 0)
            config = str(state.get("config", "single_agent"))
            status = str(state.get("status", "completed"))
            circuit_breaker = bool(state.get("circuit_breaker_tripped", False))

            cost_usd = float(state.get("cost_usd", 0.0) or 0.0)
            p_tokens = int(state.get("tokens_prompt", 0) or 0)
            c_tokens = int(state.get("tokens_completion", 0) or 0)

            # 1. Root observation
            root = self._client.start_observation(
                name=f"review_pipeline:{config}",
                as_type="chain",
                input={"owner": owner, "repo": repo, "pull_number": pull_number, "config": config},
                output={
                    "status": status,
                    "final_findings_count": len(state.get("final_findings", []) or []),
                    "circuit_breaker_tripped": circuit_breaker,
                    "circuit_breaker_reason": state.get("circuit_breaker_reason"),
                },
                metadata={
                    "review_id": state.get("review_id"),
                    "model": state.get("model", ""),
                    "dry_run": state.get("dry_run", False),
                },
                usage_details={"input": p_tokens, "output": c_tokens, "total": p_tokens + c_tokens},
                cost_details={"total": cost_usd},
            )

            # 2. Child node observations
            for node in trace_report.nodes if trace_report else []:
                node_name = getattr(node, "node", "unknown")
                as_type = "agent" if "reviewer" in node_name or node_name == "judge" else "span"
                child = root.start_observation(
                    name=node_name,
                    as_type=as_type,
                    output={"error": getattr(node, "error", None)},
                    metadata={
                        "model": getattr(node, "model", None),
                        "latency_seconds": getattr(node, "latency_seconds", 0.0),
                        "circuit_breaker_tripped": getattr(node, "circuit_breaker_tripped", False),
                        "circuit_breaker_reason": getattr(node, "circuit_breaker_reason", None),
                    },
                    usage_details={
                        "input": getattr(node, "tokens_prompt", 0),
                        "output": getattr(node, "tokens_completion", 0),
                        "total": getattr(node, "tokens_total", 0),
                    },
                    cost_details={"total": getattr(node, "cost_usd", 0.0)},
                )
                child.end()

            root.end()
            self._client.flush()
            return getattr(root, "id", "recorded")
        except Exception as exc:
            logger.warning("Langfuse trace_pipeline failed (continuing gracefully): %s", exc)
            return None

    def trace_llm_generation(
        self,
        model: str,
        prompt: str,
        response: str,
        cost_usd: float = 0.0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Record an individual LLM prompt/completion observation."""
        if not self.is_enabled():
            return None

        try:
            obs = self._client.start_observation(
                name=f"llm:{model}",
                as_type="generation",
                model=model,
                input=prompt,
                output=response,
                usage_details={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": prompt_tokens + completion_tokens,
                },
                cost_details={"total": cost_usd},
                metadata=metadata or {},
            )
            obs.end()
            return getattr(obs, "id", "recorded")
        except Exception as exc:
            logger.warning("Langfuse trace_llm_generation failed (ignoring): %s", exc)
            return None

    def flush(self) -> None:
        if self._client is not None:
            try:
                self._client.flush()
            except Exception as exc:
                logger.warning("Langfuse flush failed (ignoring): %s", exc)

    def shutdown(self) -> None:
        if self._client is not None:
            try:
                self._client.shutdown()
            except Exception as exc:
                logger.warning("Langfuse shutdown failed (ignoring): %s", exc)


# Module-level tracer singleton cache
_GLOBAL_TRACER: BaseTracer | None = None


def get_tracer(settings: Settings | None = None) -> BaseTracer:
    """Retrieve or initialize the active application tracer.

    Returns NoopTracer if langfuse_enabled is False or credentials missing.
    """
    global _GLOBAL_TRACER
    if _GLOBAL_TRACER is not None:
        return _GLOBAL_TRACER

    cfg = settings or get_settings()
    if not cfg.langfuse_enabled or not (cfg.langfuse_public_key and cfg.langfuse_secret_key):
        return NoopTracer()

    _GLOBAL_TRACER = LangfuseTracer(
        public_key=cfg.langfuse_public_key,
        secret_key=cfg.langfuse_secret_key,
        host=cfg.langfuse_host,
    )
    return _GLOBAL_TRACER


def set_tracer(tracer: BaseTracer | None) -> None:
    """Explicitly set global tracer instance for testing or custom lifecycles."""
    global _GLOBAL_TRACER
    _GLOBAL_TRACER = tracer


def reset_tracer() -> None:
    """Reset the global tracer singleton to uninitialized state."""
    global _GLOBAL_TRACER
    _GLOBAL_TRACER = None
