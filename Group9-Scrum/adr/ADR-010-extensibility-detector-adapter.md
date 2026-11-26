# ADR-010: Extensibility through a Detector Adapter and a stable rule registry

- **Status:** Accepted (draft to be committed to the fork's `docs/adr/`)
- **Date:** 2026-11-09
- **NFR:** Extensibility — adding a detector must not require changes to the comparison engine.
- **Related:** `finding.py`, `rule_registry.py`, `delta.py`, `docs/rule_ids.json`,
  `tests/test_rule_coverage.py`

## Context

PyExamine ships three detectors (code, structural, architectural) with 47 rules. The fork adds a
comparison layer. If the comparison layer knew about detector internals, every upstream change or
new rule would require editing the delta engine — and the fork would drift from upstream, breaking
the byte-compatibility guarantee (US-06).

The NFR is measurable: “add a detector/rule and do not touch `delta.py`”.

## Decision

Insert a **detector adapter boundary** built on three pieces:

1. **Unified `Finding`** (`finding.py`): `type`, `name`, `description`, `file_path`,
   `module_class`, `line_number`, `severity`, plus normalised fields used by identity and metrics.
   All three detectors are adapted into this type; upstream detection code stays byte-identical.
2. **Stable rule registry** (`rule_registry.py`): 47 ids of the form
   `pyex-<category>-<slug>`, generated from `docs/rule_ids.json`, with a mapping from legacy
   `PX-*` numbers. Output formats (SARIF rule ids, JSON, Markdown) consume the registry, never
   ad-hoc strings.
3. **Detector-agnostic engine**: `fingerprint.py`, `risk.py` and `delta.py` operate only on
   `Finding`. Adding a rule means adding a descriptor and emitting the same finding shape — no
   engine change.

The contract is enforced by a coverage test: every rule id the detectors can emit must exist in
the registry, and the registry must contain no orphan descriptor.

## Alternatives considered

- **Per-detector diff logic.** Rejected: duplicates matching, three places to fix every bug, and
  the fork would diverge from upstream.
- **Let each detector emit its own JSON schema.** Rejected: outputs become unstable; downstream
  risk/SARIF code grows a switch per detector.
- **Dynamic plugin discovery (entry points).** Rejected for this release: premature for 47 rules
  in one package; it adds failure modes (a broken plugin silently disables a detector). The
  adapter interface is the extension point we need.
- **Uppercase PX ids as the public identity.** Rejected: legacy numbers are not stable across
  upstream releases; a semantic id survives renumbering.

## Consequences

- **Positive:** upstream detectors can be updated independently; new formats reuse the registry;
  SARIF consumers get stable ids; a new detector is a weekend task, not a refactor.
- **Neutral:** one adapter function per detector (three small functions) must be maintained.
- **Negative:** detector-specific semantics that do not fit `Finding` (e.g. cross-file dead code)
  must be expressed as metadata/metrics; this is a constraint on future detectors, not a blocker.

## Verification

- `tests/test_rule_coverage.py` — all 47 ids resolve; no orphan descriptor.
- `tests/test_sarif.py` — rule ids come from the registry; `--all-rules` emits 47 descriptors.
- Code review rule: a PR that adds a rule without touching `delta.py` is the acceptance test for
  this ADR.