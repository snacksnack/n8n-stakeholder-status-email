"""Prompt-contract and golden evals for the stakeholder status email (RC1-258).

Two layers, split by what they cost:

* **Layer 1 — the contract.** Free, no credentials, runs on every push. Asserts
  the prompt's stated output format and the downstream parser's regexes still
  agree. This is the one that catches the failure that ships a malformed email
  to real stakeholders.
* **Layer 2 — prompt goldens.** Billed. Binds fixture values into the real
  prompt, calls the Messages API, and scores must-say / must-not-say.

End-to-end execution through the webhook trigger is deliberately **not** here —
see `docs/rc1-258-evals.md` for why, and what evidence would justify it.
"""

from __future__ import annotations

__version__ = "0.1.0"
