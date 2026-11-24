"""Stable SARIF rule registry for PyExamine (47 detectors).

Generated from 02-design/rule_ids.json.  ruleId = pyex-<category>-<slug>;
slugs are derived deterministically from the upstream smell name, so an
upstream rename cannot silently renumber existing ruleIds.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class Rule:
    rule_id: str
    legacy_id: str          # PX-C01 / PX-A01 / PX-S01 (human facing)
    name: str               # detector output name, verbatim
    category: str           # code | structural | architectural


RULES: Tuple[Rule, ...] = (
    Rule('pyex-arch-cyclic-dependency', 'PX-A01', 'Cyclic Dependency', 'architectural'),
    Rule('pyex-arch-god-object', 'PX-A02', 'God Object', 'architectural'),
    Rule('pyex-arch-hub-like-dependency', 'PX-A03', 'Hub-like Dependency', 'architectural'),
    Rule('pyex-arch-orphan-module', 'PX-A04', 'Orphan Module', 'architectural'),
    Rule('pyex-arch-potential-improper-api-usage', 'PX-A05', 'Potential Improper API Usage', 'architectural'),
    Rule('pyex-arch-potential-redundant-abstractions', 'PX-A06', 'Potential Redundant Abstractions', 'architectural'),
    Rule('pyex-arch-scattered-functionality', 'PX-A07', 'Scattered Functionality', 'architectural'),
    Rule('pyex-arch-unstable-dependency', 'PX-A08', 'Unstable Dependency', 'architectural'),
    Rule('pyex-code-alternative-classes-with-different-interfaces', 'PX-C01', 'Alternative Classes with Different Interfaces', 'code'),
    Rule('pyex-code-data-class', 'PX-C02', 'Data Class', 'code'),
    Rule('pyex-code-data-clumps', 'PX-C03', 'Data Clumps', 'code'),
    Rule('pyex-code-dead-code', 'PX-C04', 'Dead Code', 'code'),
    Rule('pyex-code-duplicate-code', 'PX-C05', 'Duplicate Code', 'code'),
    Rule('pyex-code-excessive-comments', 'PX-C06', 'Excessive Comments', 'code'),
    Rule('pyex-code-feature-envy', 'PX-C07', 'Feature Envy', 'code'),
    Rule('pyex-code-inappropriate-intimacy', 'PX-C08', 'Inappropriate Intimacy', 'code'),
    Rule('pyex-code-large-class', 'PX-C09', 'Large Class', 'code'),
    Rule('pyex-code-lazy-class', 'PX-C10', 'Lazy Class', 'code'),
    Rule('pyex-code-long-method', 'PX-C11', 'Long Method', 'code'),
    Rule('pyex-code-long-parameter-list', 'PX-C12', 'Long Parameter List', 'code'),
    Rule('pyex-code-message-chains', 'PX-C13', 'Message Chains', 'code'),
    Rule('pyex-code-middle-man', 'PX-C14', 'Middle Man', 'code'),
    Rule('pyex-code-parallel-inheritance-hierarchies', 'PX-C15', 'Parallel Inheritance Hierarchies', 'code'),
    Rule('pyex-code-potential-divergent-change', 'PX-C16', 'Potential Divergent Change', 'code'),
    Rule('pyex-code-potential-shotgun-surgery', 'PX-C17', 'Potential Shotgun Surgery', 'code'),
    Rule('pyex-code-primitive-obsession', 'PX-C18', 'Primitive Obsession', 'code'),
    Rule('pyex-code-speculative-generality', 'PX-C19', 'Speculative Generality', 'code'),
    Rule('pyex-code-switch-statements', 'PX-C20', 'Switch Statements', 'code'),
    Rule('pyex-code-temporary-field', 'PX-C21', 'Temporary Field', 'code'),
    Rule('pyex-struct-dit', 'PX-S01', 'Deep Inheritance Tree (DIT)', 'structural'),
    Rule('pyex-struct-deep-nesting', 'PX-S02', 'Deep Nesting', 'structural'),
    Rule('pyex-struct-cbo', 'PX-S03', 'High Coupling Between Object Classes (CBO)', 'structural'),
    Rule('pyex-struct-high-cyclomatic-complexity', 'PX-S04', 'High Cyclomatic Complexity', 'structural'),
    Rule('pyex-struct-high-fan-in', 'PX-S05', 'High Fan-in', 'structural'),
    Rule('pyex-struct-high-fan-out', 'PX-S06', 'High Fan-out', 'structural'),
    Rule('pyex-struct-lcom', 'PX-S07', 'High Lack of Cohesion of Methods (LCOM)', 'structural'),
    Rule('pyex-struct-loc', 'PX-S08', 'High Lines of Code (LOC)', 'structural'),
    Rule('pyex-struct-mpc', 'PX-S09', 'High Message Passing Coupling (MPC)', 'structural'),
    Rule('pyex-struct-noc', 'PX-S10', 'High Number of Classes (NOC)', 'structural'),
    Rule('pyex-struct-nocc', 'PX-S11', 'High Number of Classes (NOCC)', 'structural'),
    Rule('pyex-struct-nom', 'PX-S12', 'High Number of Methods (NOM)', 'structural'),
    Rule('pyex-struct-rfc', 'PX-S13', 'High Response for a Class (RFC)', 'structural'),
    Rule('pyex-struct-wac', 'PX-S14', 'High Weight of a Class (WAC)', 'structural'),
    Rule('pyex-struct-wmpc', 'PX-S15', 'High Weighted Methods per Class (WMPC)', 'structural'),
    Rule('pyex-struct-size2', 'PX-S16', 'Large Class (SIZE2)', 'structural'),
    Rule('pyex-struct-long-file', 'PX-S17', 'Long File', 'structural'),
    Rule('pyex-struct-too-many-branches', 'PX-S18', 'Too Many Branches', 'structural'),
)

RULES_BY_NAME: Dict[str, Rule] = {r.name: r for r in RULES}
RULES_BY_ID: Dict[str, Rule] = {r.rule_id: r for r in RULES}


_NON_WORD = re.compile(r"[^a-z0-9]+")
_PAREN_ABBR = re.compile(r"\(([A-Za-z][A-Za-z0-9]{1,9})\)")


def _slug(name: str) -> str:
    """Kebab-case slug; parenthesised abbreviations win (NOM, DIT, NOC)."""
    m = _PAREN_ABBR.search(name)
    if m:
        return m.group(1).lower()
    return _NON_WORD.sub("-", name.lower()).strip("-")


def rule_id_for(name: str, category: str) -> str:
    """Registered ruleId, or a deterministic fallback for unknown smells."""
    rule = RULES_BY_NAME.get(name)
    if rule is not None:
        return rule.rule_id
    return "pyex-%s-%s" % (category, _slug(name))


def rule_for(name: str, category: str) -> Rule:
    rule = RULES_BY_NAME.get(name)
    if rule is not None:
        return rule
    return Rule(rule_id_for(name, category), "PX-?", name, category)

