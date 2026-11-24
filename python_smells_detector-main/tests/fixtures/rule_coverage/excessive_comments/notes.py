"""A module whose comments outweigh its code.

Every block below is six comment lines long, which is what the detector means
by "large": more than five consecutive comment lines.  Six such blocks against
three lines of actual code is the shape that trips the ratio threshold.
"""

VALUE = 1

# First block: why this module exists at all, what problem it solves, which
# subsystem calls it, what the historical alternative was, and what would
# break if it were removed.  Six lines is the point: reviewers stop reading
# after two, and the detector should say so.
# Adding a seventh line here changes nothing about the behaviour.
# It is still a comment.

# Second block: design rationale for the constant above, including the
# decision to keep it a module-level global instead of a class attribute,
# the two rejected alternatives, and the benchmark that motivated the
# choice.  None of this is exercised by a test.
# It is still a comment.
# Six lines again.

# Third block: rollout notes.  Which release introduced the constant, who
# reviewed it, what the canary looked like, and how to roll back if the
# value turns out to be wrong during the next incident window.
# Six lines again.
# Nobody reads this during an incident.
# The value has never been changed.

# Fourth block: naming discussion.  The team debated ``VALUE`` versus
# ``DEFAULT_VALUE`` versus ``MAGIC_VALUE`` and settled on the shortest one
# because the module namespace already carries the meaning, while the
# longer names pushed call sites past the line limit.
# Settled, for now.
# Revisit only if a second constant appears.

# Fifth block: performance measurements taken on the reference machine,
# with the interpreter version, the corpus, and the warm-up procedure.
# These numbers are informational and not asserted anywhere.
# They may be stale.
# They are probably stale.
# Re-measure before quoting them.

# Sixth block: references to the upstream discussion threads, the issue
# numbers that touched this file, and the person who owns the follow-up
# work.  Kept in a comment because the project has no changelog policy.
# End of block.
# Really the end.
# Yes.


def compute(value):
    return value + VALUE
