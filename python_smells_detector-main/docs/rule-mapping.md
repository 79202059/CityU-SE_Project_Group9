| # | SARIF ruleId | smell name (as reported) | category | source file |
|---|---|---|---|---|
| PX-A01 | `pyex-arch-cyclic-dependency` | Cyclic Dependency | architectural | architectural_smell_detector.py |
| PX-A02 | `pyex-arch-god-object` | God Object | architectural | architectural_smell_detector.py |
| PX-A03 | `pyex-arch-hub-like-dependency` | Hub-like Dependency | architectural | architectural_smell_detector.py |
| PX-A04 | `pyex-arch-orphan-module` | Orphan Module | architectural | architectural_smell_detector.py |
| PX-A05 | `pyex-arch-potential-improper-api-usage` | Potential Improper API Usage | architectural | architectural_smell_detector.py |
| PX-A06 | `pyex-arch-potential-redundant-abstractions` | Potential Redundant Abstractions | architectural | architectural_smell_detector.py |
| PX-A07 | `pyex-arch-scattered-functionality` | Scattered Functionality | architectural | architectural_smell_detector.py |
| PX-A08 | `pyex-arch-unstable-dependency` | Unstable Dependency | architectural | architectural_smell_detector.py |
| PX-C01 | `pyex-code-alternative-classes-with-different-interfaces` | Alternative Classes with Different Interfaces | code | code_smell_detector.py |
| PX-C02 | `pyex-code-data-class` | Data Class | code | code_smell_detector.py |
| PX-C03 | `pyex-code-data-clumps` | Data Clumps | code | code_smell_detector.py |
| PX-C04 | `pyex-code-dead-code` | Dead Code | code | code_smell_detector.py |
| PX-C05 | `pyex-code-duplicate-code` | Duplicate Code | code | code_smell_detector.py |
| PX-C06 | `pyex-code-excessive-comments` | Excessive Comments | code | code_smell_detector.py |
| PX-C07 | `pyex-code-feature-envy` | Feature Envy | code | code_smell_detector.py |
| PX-C08 | `pyex-code-inappropriate-intimacy` | Inappropriate Intimacy | code | code_smell_detector.py |
| PX-C09 | `pyex-code-large-class` | Large Class | code | code_smell_detector.py |
| PX-C10 | `pyex-code-lazy-class` | Lazy Class | code | code_smell_detector.py |
| PX-C11 | `pyex-code-long-method` | Long Method | code | code_smell_detector.py |
| PX-C12 | `pyex-code-long-parameter-list` | Long Parameter List | code | code_smell_detector.py |
| PX-C13 | `pyex-code-message-chains` | Message Chains | code | code_smell_detector.py |
| PX-C14 | `pyex-code-middle-man` | Middle Man | code | code_smell_detector.py |
| PX-C15 | `pyex-code-parallel-inheritance-hierarchies` | Parallel Inheritance Hierarchies | code | code_smell_detector.py |
| PX-C16 | `pyex-code-potential-divergent-change` | Potential Divergent Change | code | code_smell_detector.py |
| PX-C17 | `pyex-code-potential-shotgun-surgery` | Potential Shotgun Surgery | code | code_smell_detector.py |
| PX-C18 | `pyex-code-primitive-obsession` | Primitive Obsession | code | code_smell_detector.py |
| PX-C19 | `pyex-code-speculative-generality` | Speculative Generality | code | code_smell_detector.py |
| PX-C20 | `pyex-code-switch-statements` | Switch Statements | code | code_smell_detector.py |
| PX-C21 | `pyex-code-temporary-field` | Temporary Field | code | code_smell_detector.py |
| PX-S01 | `pyex-struct-dit` | Deep Inheritance Tree (DIT) | structural | structural_smell_detector.py |
| PX-S02 | `pyex-struct-deep-nesting` | Deep Nesting | structural | structural_smell_detector.py |
| PX-S03 | `pyex-struct-cbo` | High Coupling Between Object Classes (CBO) | structural | structural_smell_detector.py |
| PX-S04 | `pyex-struct-high-cyclomatic-complexity` | High Cyclomatic Complexity | structural | structural_smell_detector.py |
| PX-S05 | `pyex-struct-high-fan-in` | High Fan-in | structural | structural_smell_detector.py |
| PX-S06 | `pyex-struct-high-fan-out` | High Fan-out | structural | structural_smell_detector.py |
| PX-S07 | `pyex-struct-lcom` | High Lack of Cohesion of Methods (LCOM) | structural | structural_smell_detector.py |
| PX-S08 | `pyex-struct-loc` | High Lines of Code (LOC) | structural | structural_smell_detector.py |
| PX-S09 | `pyex-struct-mpc` | High Message Passing Coupling (MPC) | structural | structural_smell_detector.py |
| PX-S10 | `pyex-struct-noc` | High Number of Classes (NOC) | structural | structural_smell_detector.py |
| PX-S11 | `pyex-struct-nocc` | High Number of Classes (NOCC) | structural | structural_smell_detector.py |
| PX-S12 | `pyex-struct-nom` | High Number of Methods (NOM) | structural | structural_smell_detector.py |
| PX-S13 | `pyex-struct-rfc` | High Response for a Class (RFC) | structural | structural_smell_detector.py |
| PX-S14 | `pyex-struct-wac` | High Weight of a Class (WAC) | structural | structural_smell_detector.py |
| PX-S15 | `pyex-struct-wmpc` | High Weighted Methods per Class (WMPC) | structural | structural_smell_detector.py |
| PX-S16 | `pyex-struct-size2` | Large Class (SIZE2) | structural | structural_smell_detector.py |
| PX-S17 | `pyex-struct-long-file` | Long File | structural | structural_smell_detector.py |
| PX-S18 | `pyex-struct-too-many-branches` | Too Many Branches | structural | structural_smell_detector.py |

Generated from `rule_ids.json`; the ruleId is derived from the smell
name, so an upstream rename cannot silently shift an existing id.
