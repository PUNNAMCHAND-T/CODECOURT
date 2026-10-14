"""Prompt templates and untrusted content boundary utilities."""

from backend.app.agents.prompts.delimiters import (
    DELIMITER_END_DIFF,
    DELIMITER_END_FILE,
    DELIMITER_END_METADATA,
    DELIMITER_START_DIFF,
    DELIMITER_START_FILE,
    DELIMITER_START_METADATA,
    sanitize_untrusted_text,
    wrap_untrusted_diff,
    wrap_untrusted_metadata,
)
from backend.app.agents.prompts.maintainability_v1 import (
    MAINTAINABILITY_AGENT_SYSTEM_PROMPT_V1,
    MAINTAINABILITY_PROMPT_VERSION,
    build_maintainability_agent_prompt,
)
from backend.app.agents.prompts.performance_v1 import (
    PERFORMANCE_AGENT_SYSTEM_PROMPT_V1,
    PERFORMANCE_PROMPT_VERSION,
    build_performance_agent_prompt,
)
from backend.app.agents.prompts.security_v1 import (
    SECURITY_AGENT_SYSTEM_PROMPT_V1,
    SECURITY_PROMPT_VERSION,
    build_security_agent_prompt,
)
from backend.app.agents.prompts.single_agent_v1 import (
    PROMPT_VERSION,
    SINGLE_AGENT_SYSTEM_PROMPT_V1,
    build_single_agent_prompt,
)

__all__ = [
    "DELIMITER_END_DIFF",
    "DELIMITER_END_FILE",
    "DELIMITER_END_METADATA",
    "DELIMITER_START_DIFF",
    "DELIMITER_START_FILE",
    "DELIMITER_START_METADATA",
    "MAINTAINABILITY_AGENT_SYSTEM_PROMPT_V1",
    "MAINTAINABILITY_PROMPT_VERSION",
    "PERFORMANCE_AGENT_SYSTEM_PROMPT_V1",
    "PERFORMANCE_PROMPT_VERSION",
    "PROMPT_VERSION",
    "SECURITY_AGENT_SYSTEM_PROMPT_V1",
    "SECURITY_PROMPT_VERSION",
    "SINGLE_AGENT_SYSTEM_PROMPT_V1",
    "build_maintainability_agent_prompt",
    "build_performance_agent_prompt",
    "build_security_agent_prompt",
    "build_single_agent_prompt",
    "sanitize_untrusted_text",
    "wrap_untrusted_diff",
    "wrap_untrusted_metadata",
]
