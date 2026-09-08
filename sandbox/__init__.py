"""Sandboxed execution of participant bot code.

Three layers, applied in order:

1. ``policy``  — static AST analysis of the submitted file (import allowlist,
   no dunder attribute access, no ``eval``/``exec``/``open``/``getattr``).
   Runs at submission time, so a bad file never reaches the runner.
2. ``child``   — the executing process: rlimits (address space, CPU, no files,
   no forks), network neutered, stdout detached from the protocol channel.
3. ``runner``  — the parent side: one child per bot, per-round wall-clock
   timeout enforced by killing the child, consecutive-failure disqualification.

Layer 2's argv is chosen by ``runner.detect_isolation()`` — Docker if present,
otherwise a network namespace via ``unshare``, otherwise a dedicated low-privilege
user via ``sudo``, otherwise a plain subprocess. See ``docs/SECURITY.md``.
"""
