"""Two inheritance hierarchies that grow in lockstep.

Adding ``Rect`` to ``Shape`` forces adding ``Rect`` to ``Style``.  The
detector matches the suffix left over after stripping the base-class name
(``ShapeRect`` -> ``Rect``, ``StyleRect`` -> ``Rect``) and then checks that
the sibling subclasses expose a comparable method set, so both families
below expose the same three method names.
"""


class Shape:
    def describe(self):
        raise NotImplementedError

    def measure(self):
        raise NotImplementedError

    def ratio(self):
        raise NotImplementedError


class ShapeRect(Shape):
    def describe(self):
        return "rect"

    def measure(self):
        return 1

    def ratio(self):
        return 4


class ShapeCircle(Shape):
    def describe(self):
        return "circle"

    def measure(self):
        return 3

    def ratio(self):
        return 6


class Style:
    def describe(self):
        raise NotImplementedError

    def measure(self):
        raise NotImplementedError

    def ratio(self):
        raise NotImplementedError


class StyleRect(Style):
    def describe(self):
        return "red rectangle"

    def measure(self):
        return "solid"

    def ratio(self):
        return "1:1"


class StyleCircle(Style):
    def describe(self):
        return "blue circle"

    def measure(self):
        return "dashed"

    def ratio(self):
        return "1:2"
