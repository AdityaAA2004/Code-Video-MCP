"""LLM access for the three generative pipeline stages.

Three call sites, all funnelled through :class:`~.client.LLMClient`:

* ``build_storyboard``        -- structured output constrained by the storyboard schema
* ``generate_remotion_code``  -- slot filling against the checked-in scaffold
* ``fix_errors``              -- repair pass fed by ``tsc``/eslint output

Import from :mod:`.client` and :mod:`.prompts` directly; nothing is re-exported.
"""
