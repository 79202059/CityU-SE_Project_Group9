# Rule coverage fixtures

Four real corpora (flask, requests, click and PyExamine's own `src/`) reach
**40 of the 47** rules in `code_quality_analyzer/rule_registry.py`.  The
seven rules below never fired on any corpus, which means a regression in
them would be invisible.  Each directory here is the smallest project that
makes exactly one of those rules fire; `tests/test_rule_coverage.py` is the
executable version of this table.

| fixture | rule id | why it fires |
| --- | --- | --- |
| `data_class/` | `pyex-code-data-class` | one class exposing only `get_*`/`set_*` accessors (3 pairs, 6 methods ≥ `DATA_CLASS_METHODS` 4), no behaviour, and a name that avoids the `*DTO`/`*Model`/`*Entity`/`*Record` exemptions |
| `excessive_comments/` | `pyex-code-excessive-comments` | six comment blocks of six lines against three lines of code: ratio 720% and 6 large blocks (> `LARGE_COMMENT_BLOCKS` 5) |
| `high_fanout/` | `pyex-struct-high-fan-out` | a hub importing sixteen local modules, more than `MAX_FANOUT` 15 non-stdlib dependencies |
| `intimacy/` | `pyex-code-inappropriate-intimacy` | `Auditor` reads three private fields of `Account` (shared 3 > `INAPPROPRIATE_INTIMACY_SHARED` 2), no inheritance or composition between them |
| `middle_man/` | `pyex-code-middle-man` | `OrderService` forwards 3 of its 4 methods straight to `self._repo` (delegation ratio 0.75 > `MIDDLE_MAN_RATIO` 0.5), and the class name avoids the Proxy/Delegate/Adapter/Facade exemptions |
| `parallel_inheritance/` | `pyex-code-parallel-inheritance-hierarchies` | `ShapeRect`/`ShapeCircle` and `StyleRect`/`StyleCircle` correspond by suffix once the base name is stripped, and share three method names (Jaccard 1.0 > 0.3) |
| `redundant_abstractions/` | `pyex-arch-potential-redundant-abstractions` | `alpha.py` and `beta.py` expose the same four public function names (Jaccard 1.0 ≥ `REDUNDANT_ABSTRACTION_SIMILARITY` 0.7) |

## Notes

- `high_fanout/hub.py` is the checked-in sample.  The test builds the same
  hub, plus the sixteen `mod_NN.py` modules it imports, in
  `tests/_tmp_rule_coverage/` so the fixture directory stays small; a test
  asserts the checked-in sample still has the same import list.
- A negative test pins the threshold: fifteen local modules must **not**
  raise the fan-out rule.
- Each fixture is deliberately tiny.  Some of them also trip neighbouring
  rules (for example `parallel_inheritance/` alone is not enough — the
  detector needs the shared method names), and the test only asserts the
  rule it is here for, not an exact finding count.
