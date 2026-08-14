"""LLM access for the three generative pipeline stages.

Important consequence of FastMCP 4: ``ctx.sample()`` (server-initiated sampling
through the host) has been **removed**. A server that needs a model must call one
itself. So this package owns a direct provider client and its own credentials,
rather than borrowing the host's model.

Three call sites, all funnelled through :class:`LLMClient`:

* ``build_storyboard``        -- structured output constrained by the storyboard schema
* ``generate_remotion_code``  -- slot filling against the checked-in scaffold
* ``fix_errors``              -- repair pass fed by ``tsc``/eslint output

Keeping the interface a Protocol means tests substitute a canned client and
never hit the network.
"""

from __future__ import annotations

from code_explain_video_mcp.llm.client import LLMClient, LLMResponse, StructuredRequest

__all__ = ["LLMClient", "LLMResponse", "StructuredRequest"]
