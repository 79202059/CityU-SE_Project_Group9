"""A module that imports sixteen local collaborators.

The structural "High Fan-out" metric counts distinct non-stdlib modules a
module depends on; the bundled threshold is fifteen.  Generating the sixteen
modules in the fixture is cheaper than checking in sixteen trivial files, so
``conftest``-style helpers create them at test time.  This file is only the
hub and is not imported by anything.
"""

import mod_00
import mod_01
import mod_02
import mod_03
import mod_04
import mod_05
import mod_06
import mod_07
import mod_08
import mod_09
import mod_10
import mod_11
import mod_12
import mod_13
import mod_14
import mod_15


def collect():
    return [
        mod_00.value(),
        mod_01.value(),
        mod_02.value(),
        mod_03.value(),
        mod_04.value(),
        mod_05.value(),
        mod_06.value(),
        mod_07.value(),
        mod_08.value(),
        mod_09.value(),
        mod_10.value(),
        mod_11.value(),
        mod_12.value(),
        mod_13.value(),
        mod_14.value(),
        mod_15.value(),
    ]
