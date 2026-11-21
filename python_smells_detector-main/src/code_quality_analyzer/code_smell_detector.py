import logging
import operator
import re
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations, product

import astroid
from astroid import exceptions as astroid_exceptions
from astroid import nodes

from .exceptions import CodeAnalysisError

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class CodeSmell:
    name: str
    description: str
    file_path: str
    module_class: str
    line_number: int
    severity: str = ''


class CodeSmellDetector:
    """
    A class to detect various code smells in Python source code.

    This class analyzes Python source code for common code smells and anti-patterns,
    providing a comprehensive report on potential issues in the codebase.

    Attributes:
        code_smells (list): A list to store detected code smells.
        thresholds (dict): A dictionary of threshold values for various code smell detections.
        file_content (list): A list of strings representing the content of the analyzed file.
    """

    def __init__(self, thresholds):
        """
        Initialize the CodeSmellDetector with given thresholds.

        Args:
            thresholds (dict): A dictionary of threshold values for various code smell detections.
        """
        self.code_smells = []
        self.thresholds = thresholds
        # Cross-file accumulation for smells needing multi-file context
        self._global_class_methods = defaultdict(list)
        self._global_param_groups = defaultdict(list)
        self._global_code_blocks = defaultdict(list)
        self._global_class_info = {}
        self._global_class_hierarchies = defaultdict(list)

        # Direction A: project-wide scope/reference registry accumulated per file
        # and finalized in detect_cross_file_smells(). Replaces per-file,
        # name-only guessing with resolved definitions, imports, and references.
        self._project_defs = {}           # file_path -> {"functions": set, "classes": set}
        self._project_import_aliases = {} # file_path -> {local_alias: origin}
        self._project_exports = set()     # names listed in any module's __all__
        self._project_references = set()   # every name referenced anywhere in the project
        self._dead_candidates = []        # (name, file_path, lineno, public_decorator, exported)

    def detect_smells(self, file_path):
        """
        Detect code smells in the given file.
        """
        detection_methods = [
            (self.detect_long_methods, "detect_long_methods"),
            (self.detect_large_classes, "detect_large_classes"),
            (self.detect_primitive_obsession, "detect_primitive_obsession"),
            (self.detect_long_parameter_lists, "detect_long_parameter_lists"),
            (self.detect_data_clumps, "detect_data_clumps"),
            (self.detect_switch_statements, "detect_switch_statements"),
            (self.detect_temporary_fields, "detect_temporary_fields"),
            (self.detect_alternative_classes, "detect_alternative_classes"),
            (self.detect_divergent_change, "detect_divergent_change"),
            (self.detect_parallel_inheritance, "detect_parallel_inheritance"),
            (self.detect_shotgun_surgery, "detect_shotgun_surgery"),
            (self.detect_comments, "detect_comments"),
            (self.detect_duplicate_code, "detect_duplicate_code"),
            (self.detect_speculative_generality, "detect_speculative_generality"),
            (self.detect_dead_code, "detect_dead_code"),
            (self.detect_feature_envy, "detect_feature_envy"),
            (self.detect_inappropriate_intimacy, "detect_inappropriate_intimacy"),
            (self.detect_message_chains, "detect_message_chains"),
            (self.detect_middle_man, "detect_middle_man"),
            (self.detect_magic_numbers, "detect_magic_numbers"),
            (self.detect_magic_strings, "detect_magic_strings"),
            (self.detect_constant_conditions, "detect_constant_conditions")
        ]

        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()

            try:
                module = astroid.parse(content)
            except astroid_exceptions.AstroidSyntaxError as e:
                logger.error(f"Syntax error in {file_path}: {str(e)}")
                raise CodeAnalysisError(
                    message=f"Failed to parse Python file: {str(e)}",
                    file_path=file_path,
                    line_number=getattr(e, 'lineno', None)
                )

            self.file_content = content.split('\n')

            # Direction A: record this file's definitions, imports, and references
            # into the project-wide registry before per-file detection runs.
            self._register_file_scope(module, file_path)

            # Run each detection method
            for detect_method, method_name in detection_methods:
                try:
                    logger.debug(f"Running {method_name} on {file_path}")
                    detect_method(module, file_path)
                except Exception as e:
                    logger.error(
                        f"Error in {method_name} analyzing {file_path}: {str(e)}",
                        exc_info=True
                    )
                    raise CodeAnalysisError(
                        message=f"Error in {method_name}: {str(e)}",
                        file_path=file_path,
                        function_name=method_name
                    )

        except UnicodeDecodeError as e:
            logger.error(f"Encoding error in {file_path}: {str(e)}")
            raise CodeAnalysisError(
                message=f"File encoding error: {str(e)}",
                file_path=file_path
            )
        except Exception as e:
            logger.error(f"Unexpected error analyzing {file_path}: {str(e)}", exc_info=True)
            raise CodeAnalysisError(
                message=f"Unexpected error: {str(e)}",
                file_path=file_path
            )

    def _register_file_scope(self, module, file_path):
        """Collect definitions, import aliases, exports, and references for one file.

        Feeds the project-wide registry used by the scope-aware detectors
        (Direction A). Runs per file inside detect_smells(); cross-file
        finalization happens later in detect_cross_file_smells().
        """
        defs = {"functions": set(), "classes": set()}
        import_aliases = {}
        references = set()

        # Top-level definitions provided by this file
        for node in module.body:
            if isinstance(node, nodes.FunctionDef):
                defs["functions"].add(node.name)
            elif isinstance(node, nodes.ClassDef):
                defs["classes"].add(node.name)

        # Import aliases: `import x` and `from m import y [as z]`
        # astroid exposes Import/ImportFrom.names as (name, asname) tuples.
        for node in module.nodes_of_class(nodes.Import):
            for name, asname in node.names:
                local = asname or name
                import_aliases[local] = name
                references.add(local)
        for node in module.nodes_of_class(nodes.ImportFrom):
            for name, asname in node.names:
                local = asname or name
                origin = f"{node.modname}.{name}" if node.modname else name
                import_aliases[local] = origin
                references.add(local)

        # Names exported via `__all__` are part of the public API
        for node in module.nodes_of_class(nodes.Assign):
            targets = node.targets
            if (len(targets) == 1 and isinstance(targets[0], nodes.AssignName)
                    and targets[0].name == '__all__'
                    and isinstance(node.value, nodes.List)):
                for elt in node.value.elts:
                    if isinstance(elt, nodes.Const) and isinstance(elt.value, str):
                        self._project_exports.add(elt.value)

        # Every referenced Name (calls, receivers, bases, decorators) and attribute
        for node in module.nodes_of_class(nodes.Name):
            if node.name != 'self':
                references.add(node.name)
        for node in module.nodes_of_class(nodes.Attribute):
            references.add(node.attrname)

        self._project_defs[file_path] = defs
        self._project_import_aliases[file_path] = import_aliases
        self._project_references.update(references)

    def _all_defined_names(self):
        """Union of all function and class names defined across parsed files."""
        names = set()
        for defs in self._project_defs.values():
            names.update(defs["functions"])
            names.update(defs["classes"])
        return names

    def detect_long_methods(self, module, file_path):
        """
        Detect long methods in the given module.
        """
        for node in module.nodes_of_class(nodes.FunctionDef):
            # Skip property decorators and simple getter/setters
            if node.decorators:
                is_property = False
                for decorator in node.decorators.nodes:
                    # Handle both direct name and call decorators
                    if isinstance(decorator, nodes.Name) and decorator.name == 'property':
                        is_property = True
                        break
                    elif isinstance(decorator, nodes.Call) and isinstance(decorator.func, nodes.Name) and decorator.func.name == 'property':
                        is_property = True
                        break
                if is_property:
                    continue

            # Count non-empty, non-comment lines
            actual_lines = 0
            for line_no in range(node.fromlineno, node.tolineno + 1):
                if line_no <= len(self.file_content):
                    line = self.file_content[line_no - 1].strip()
                    if line and not line.startswith('#'):
                        actual_lines += 1

            if actual_lines > self.thresholds["LONG_METHOD_LINES"]:
                parent_class = node.parent.name if isinstance(node.parent, nodes.ClassDef) else None
                display_name = f"{parent_class}.{node.name}" if parent_class else node.name
                self.code_smells.append(CodeSmell(
                    name="Long Method",
                    description=f"'{display_name}' has {actual_lines} lines in {file_path} at line {node.lineno}",
                    file_path=file_path,
                    module_class=display_name,
                    line_number=node.lineno
                ))

    def detect_large_classes(self, module, file_path):
        """
        Detect large classes in the given module.
        """
        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip data classes and exception classes
            is_dataclass = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if isinstance(decorator, nodes.Name) and decorator.name == 'dataclass':
                        is_dataclass = True
                        break
                    elif isinstance(decorator, nodes.Call):
                        if isinstance(decorator.func,
                                      nodes.Name) and decorator.func.name == 'dataclass':
                            is_dataclass = True
                            break
                    elif isinstance(decorator, nodes.Attribute):
                        if decorator.attrname == 'dataclass':
                            is_dataclass = True
                            break

            if (is_dataclass or
                    any(base.name.endswith('Exception') for base in node.bases if isinstance(base, nodes.Name))):
                continue

            # Count non-trivial methods (exclude simple getters/setters)
            non_trivial_methods = []
            for method in node.body:
                if isinstance(method, nodes.FunctionDef):
                    # Skip magic methods
                    if method.name.startswith('__') and method.name.endswith('__'):
                        continue
                    # Skip simple getters/setters
                    if len(method.body) == 1 and isinstance(
                            method.body[0], (nodes.Return, nodes.Assign)):
                        continue
                    non_trivial_methods.append(method)

            if len(non_trivial_methods) > self.thresholds["LARGE_CLASS_METHODS"]:
                self.add_smell(
                    name="Large Class",
                    description=f"'{node.name}' has {len(non_trivial_methods)} non-trivial methods in {file_path}",
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno
                )

    PRIMITIVE_TYPE_NAMES = frozenset({'int', 'float', 'str', 'bool', 'bytes', 'complex'})

    def _annotation_map(self, node):
        """Map each positional parameter to its annotation node (or None).

        astroid stores annotations in a flat list that, depending on version,
        aligns either with ``posonlyargs + args`` or with ``args`` alone. Both
        layouts are handled so annotations are never misattributed.
        """
        posonly = list(getattr(node.args, 'posonlyargs', None) or [])
        args = list(node.args.args)
        annotations = list(node.args.annotations or [])
        if len(annotations) == len(posonly) + len(args):
            positional = posonly + args
        elif len(annotations) == len(args):
            positional = args
        else:
            positional = args
            annotations = []
        return {id(arg): (annotations[i] if i < len(annotations) else None)
                for i, arg in enumerate(positional)}, positional

    @classmethod
    def _is_primitive_annotation(cls, annotation):
        """True when the annotation names a builtin scalar type."""
        if isinstance(annotation, nodes.Name):
            return annotation.name in cls.PRIMITIVE_TYPE_NAMES
        # String forward-reference such as `a: "int"`
        if isinstance(annotation, nodes.Const) and isinstance(annotation.value, str):
            return annotation.value in cls.PRIMITIVE_TYPE_NAMES
        return False

    @staticmethod
    def _scalar_used_names(node):
        """Names used in scalar-shaped expressions (arithmetic, comparison).

        Provides the evidence used to infer a scalar type for parameters that
        carry no annotation, which is the common case in Python code.
        """
        names = set()

        for binop in node.nodes_of_class(nodes.BinOp):
            for operand in (binop.left, binop.right):
                if isinstance(operand, nodes.Name):
                    names.add(operand.name)

        for aug in node.nodes_of_class(nodes.AugAssign):
            if isinstance(aug.target, nodes.Name):
                names.add(aug.target.name)

        for cmp in node.nodes_of_class(nodes.Compare):
            left = cmp.left
            for _, right in cmp.ops:
                if isinstance(left, nodes.Name) and isinstance(right, nodes.Const):
                    names.add(left.name)
                if isinstance(right, nodes.Name) and isinstance(left, nodes.Const):
                    names.add(right.name)
                left = right

        return names

    def detect_primitive_obsession(self, module, file_path):
        """
        Detect primitive obsession in the given module.

        A positional parameter counts as primitive when it is annotated with a
        builtin scalar type, or - for unannotated parameters - when its usage
        shows scalar behaviour (arithmetic, comparison against a literal, or a
        scalar default). Unannotated code is the norm in Python, so ignoring it
        silently missed genuine cases; the two routes are reported separately so
        the inferred ones carry visible lower confidence.
        """
        for node in module.nodes_of_class(nodes.FunctionDef):
            ann_map, positional = self._annotation_map(node)

            # Skip if it's a small number of total arguments
            if len(positional) <= 3:
                continue

            if positional and positional[0].name in {'self', 'cls'}:
                positional = positional[1:]
            if not positional:
                continue

            scalar_names = self._scalar_used_names(node)

            # Defaults bind to the trailing positional parameters
            default_scalars = set()
            defaults = list(node.args.defaults or [])
            if defaults:
                for arg, default in zip(positional[-len(defaults):], defaults):
                    if isinstance(default, nodes.Const) and isinstance(
                            default.value, (int, float, str, bool, bytes, complex)):
                        default_scalars.add(arg.name)

            explicit = 0
            inferred = 0
            for arg in positional:
                if not isinstance(arg, nodes.AssignName):
                    continue
                annotation = ann_map.get(id(arg))
                if annotation is not None:
                    # An explicit non-scalar annotation is trusted over usage
                    if self._is_primitive_annotation(annotation):
                        explicit += 1
                    continue
                if arg.name in scalar_names or arg.name in default_scalars:
                    inferred += 1

            primitives = explicit + inferred
            primitive_ratio = primitives / len(positional)

            if (primitives > self.thresholds["PRIMITIVE_OBSESSION_COUNT"] and
                    primitive_ratio > 0.7):  # More than 70% primitives
                detail = (f"{explicit} annotated, {inferred} inferred from scalar usage"
                          if inferred else f"{explicit} annotated")
                self.code_smells.append(CodeSmell(
                    name="Primitive Obsession",
                    description=(f"'{node.name}' has {primitives} primitive parameters "
                                 f"({detail}) in {file_path}"),
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno
                ))

    def detect_long_parameter_lists(self, module, file_path):
        """
        Detect long parameter lists in the given module.
        """
        for node in module.nodes_of_class(nodes.FunctionDef):
            args = node.args.args

            # Skip if it's a constructor
            if node.name == '__init__':
                continue

            # Skip 'self' in method parameter count
            if args and args[0].name == 'self':
                args = args[1:]

            # Check for **kwargs or *args
            has_var_args = node.args.vararg is not None
            has_kwargs = node.args.kwarg is not None

            # Reduce severity if function has variable arguments
            threshold = (
                self.thresholds["LONG_PARAMETER_LIST"] + 2
                if (has_var_args or has_kwargs)
                else self.thresholds["LONG_PARAMETER_LIST"]
            )

            if len(args) > threshold:
                self.code_smells.append(CodeSmell(
                    name="Long Parameter List",
                    description=f"'{node.name}' has {len(args)} parameters in {file_path}",
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno
                ))

    def detect_data_clumps(self, module, file_path):
        """
        Detect data clumps in the given module.
        """
        parameter_groups = defaultdict(list)
        for node in module.nodes_of_class(nodes.FunctionDef):
            # Skip if it's a constructor or property
            if node.name == '__init__' or (node.decorators and
                                           any(isinstance(d, nodes.Name) and d.name == 'property'
                                               for d in node.decorators.nodes)):
                continue

            # Get parameters excluding self
            params = [arg.name for arg in node.args.args
                      if isinstance(arg, nodes.AssignName) and arg.name != 'self']

            # Skip if too few parameters
            if len(params) < self.thresholds["DATA_CLUMPS_THRESHOLD"]:
                continue

            # Create combinations of parameters that appear together
            for size in range(3, len(params) + 1):
                for combo in combinations(sorted(params), size):
                    parameter_groups[combo].append(node.name)

        for params, functions in parameter_groups.items():
            # Only report if parameters appear together in multiple functions
            # and represent a significant portion of each function's parameters
            if (len(functions) > 1 and
                    len(params) >= self.thresholds["DATA_CLUMPS_THRESHOLD"]):
                self.add_smell(
                    name="Data Clumps",
                    description=f"Parameters {', '.join(params)} appear together in functions: {', '.join(functions)} in {file_path}",
                    file_path=file_path,
                    module_class=', '.join(functions),
                    line_number=None,
                    severity='medium'
                )

        # Accumulate for cross-file detection
        for params, func_names in parameter_groups.items():
            for func_name in func_names:
                self._global_param_groups[params].append((func_name, file_path))

    def detect_switch_statements(self, module, file_path):
        """
        Detect switch statements in the given module.
        """
        def count_conditions(node):
            count = 1  # Start with 1 for the initial if
            for else_node in node.orelse:
                if isinstance(else_node, nodes.If):
                    count += 1
                elif isinstance(else_node, nodes.Expr):
                    continue  # Skip comments or docstrings
            return count

        for node in module.nodes_of_class(nodes.If):
            # Skip simple if/else statements
            if not node.orelse:
                continue

            # Check if this is part of a try/except block
            if any(isinstance(parent, nodes.ExceptHandler) for parent in node.node_ancestors()):
                continue

            condition_count = count_conditions(node)

            # Check for common valid patterns
            is_guard_clause = len(node.body) <= 2 and isinstance(node.test, nodes.Compare)
            is_type_check = isinstance(
                node.test, nodes.Call) and getattr(
                node.test.func, 'name', '') == 'isinstance'

            if (condition_count > self.thresholds["COMPLEX_CONDITIONAL"] and
                not is_guard_clause and
                    not is_type_check):
                self.code_smells.append(CodeSmell(
                    name="Switch Statements",
                    description=f"Complex conditional with {condition_count} branches at line {node.lineno} in {file_path}",
                    file_path=file_path,
                    module_class=None,
                    line_number=node.lineno,
                    severity='medium'
                ))

    def detect_temporary_fields(self, module, file_path):
        """
        Detect temporary fields in the given module.
        """
        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip data classes and exception classes
            is_dataclass = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if isinstance(decorator, nodes.Name) and decorator.name == 'dataclass':
                        is_dataclass = True
                        break
                    elif isinstance(decorator, nodes.Call):
                        if isinstance(decorator.func,
                                      nodes.Name) and decorator.func.name == 'dataclass':
                            is_dataclass = True
                            break
                    elif isinstance(decorator, nodes.Attribute):
                        if decorator.attrname == 'dataclass':
                            is_dataclass = True
                            break

            if (is_dataclass or
                    any(base.name.endswith('Exception') for base in node.bases if isinstance(base, nodes.Name))):
                continue

            init_fields = set()
            used_fields = set()
            cached_fields = set()  # For fields that might be used for caching

            for child in node.body:
                if isinstance(child, nodes.FunctionDef):
                    if child.name == '__init__':
                        for target in child.nodes_of_class(nodes.AssignName):
                            # Check if field has a comment indicating it's for caching
                            if any(isinstance(sibling, nodes.Expr) and
                                   isinstance(sibling.value, nodes.Const) and
                                   'cache' in str(sibling.value.value).lower()
                                   for sibling in child.body):
                                cached_fields.add(target.name)
                            else:
                                init_fields.add(target.name)
                    else:
                        used_fields.update(
                            n.attrname for n in child.nodes_of_class(nodes.Attribute)
                            if isinstance(n.expr, nodes.Name) and n.expr.name == 'self'
                        )

            # Exclude common patterns and cached fields
            temp_fields = (init_fields - used_fields - cached_fields -
                           {'logger', 'config', 'cache', '_cache'})

            if len(temp_fields) >= self.thresholds["TEMPORARY_FIELD_THRESHOLD"]:
                self.add_smell(
                    name="Temporary Field",
                    description=f"Potentially unused fields {', '.join(temp_fields)} in class '{node.name}' at line {node.lineno} in {file_path}",
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno,
                    severity='low'
                )

    def detect_alternative_classes(self, module, file_path):
        """
        Detect alternative classes with different interfaces in the given module.
        """
        class_methods = defaultdict(list)
        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip data classes, exceptions, and abstract base classes
            is_excluded = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if isinstance(decorator, nodes.Name) and decorator.name in {
                            'dataclass', 'abstractmethod'}:
                        is_excluded = True
                        break
                    elif isinstance(decorator, nodes.Call):
                        if isinstance(decorator.func, nodes.Name) and decorator.func.name in {
                                'dataclass', 'abstractmethod'}:
                            is_excluded = True
                            break
                    elif isinstance(decorator, nodes.Attribute):
                        if decorator.attrname in {'dataclass', 'abstractmethod'}:
                            is_excluded = True
                            break

            if (is_excluded or
                any(base.name.endswith(('Exception', 'ABC'))
                    for base in node.bases if isinstance(base, nodes.Name))):
                continue

            # Get non-private methods excluding standard methods
            methods = frozenset(
                n.name for n in node.mymethods()
                if not n.name.startswith('_') and
                n.name not in {'__init__', '__str__', '__repr__', '__eq__', '__hash__'}
            )

            # Skip if too few methods
            if len(methods) < 2:
                continue

            class_methods[methods].append(node.name)

        for methods, classes in class_methods.items():
            if len(classes) >= self.thresholds["ALTERNATIVE_CLASSES_THRESHOLD"]:
                # Check if classes share a common base class
                class_nodes = [
                    n for n in module.nodes_of_class(
                        nodes.ClassDef) if n.name in classes]
                share_base_class = len({base.name for n in class_nodes
                                        for base in n.bases if isinstance(base, nodes.Name)}) > 0

                if not share_base_class:
                    self.add_smell(
                        name="Alternative Classes with Different Interfaces",
                        description=f"Classes {', '.join(classes)} share similar methods {', '.join(methods)} in {file_path}",
                        file_path=file_path,
                        module_class=', '.join(classes),
                        line_number=None,
                        severity='medium'
                    )

        # Accumulate for cross-file detection
        for methods, class_names in class_methods.items():
            for class_name in class_names:
                self._global_class_methods[methods].append((class_name, file_path))

    def detect_divergent_change(self, module, file_path):
        """
        Detect divergent change in the given module.
        """
        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip data classes, exceptions, and utility classes
            is_dataclass = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if isinstance(decorator, nodes.Name) and decorator.name == 'dataclass':
                        is_dataclass = True
                        break
                    elif isinstance(decorator, nodes.Call):
                        if isinstance(decorator.func,
                                      nodes.Name) and decorator.func.name == 'dataclass':
                            is_dataclass = True
                            break
                    elif isinstance(decorator, nodes.Attribute):
                        if decorator.attrname == 'dataclass':
                            is_dataclass = True
                            break

            if (is_dataclass or
                any(base.name.endswith('Exception') for base in node.bases if isinstance(base, nodes.Name)) or
                    node.name.endswith(('Utils', 'Helper', 'Mixin'))):
                continue

            # Get method prefixes, excluding common patterns
            method_prefixes = []
            for method in node.mymethods():
                # Skip magic methods, properties, and private methods
                is_property = False
                if method.decorators:
                    for decorator in method.decorators.nodes:
                        if isinstance(decorator, nodes.Name) and decorator.name == 'property':
                            is_property = True
                            break
                        elif isinstance(decorator, nodes.Call):
                            if isinstance(decorator.func,
                                          nodes.Name) and decorator.func.name == 'property':
                                is_property = True
                                break
                        elif isinstance(decorator, nodes.Attribute):
                            if decorator.attrname == 'property':
                                is_property = True
                                break

                if (method.name.startswith('__') or is_property or method.name.startswith('_')):
                    continue

                prefix = method.name.split('_')[0]
                # Skip common CRUD and utility prefixes
                if prefix not in {'get', 'set', 'is', 'has',
                                  'validate', 'create', 'update', 'delete'}:
                    method_prefixes.append(prefix)

            unique_prefixes = set(method_prefixes)
            if (len(unique_prefixes) > self.thresholds["DIVERGENT_CHANGE_PREFIXES"] and
                    len(method_prefixes) > self.thresholds["DIVERGENT_CHANGE_METHODS"]):
                self.add_smell(
                    name="Potential Divergent Change",
                    description=f"Class '{node.name}' has {len(unique_prefixes)} different method prefixes: {', '.join(unique_prefixes)} in {file_path}",
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno,
                    severity='medium'
                )

    def detect_parallel_inheritance(self, module, file_path):
        """
        Detect parallel inheritance hierarchies in the given module.
        """
        class_hierarchies = defaultdict(list)
        class_info = {}  # Store class information for better analysis

        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip exception classes and mixins
            if (any(base.name.endswith('Exception') for base in node.bases if isinstance(base, nodes.Name)) or
                    node.name.endswith('Mixin')):
                continue

            for base in node.bases:
                if isinstance(base, nodes.Name):
                    class_hierarchies[base.name].append(node.name)
                    # Store method names for similarity comparison
                    class_info[node.name] = {m.name for m in node.mymethods()
                                             if not m.name.startswith('_')}

        # Accumulate for cross-file detection
        for base_name, child_names in class_hierarchies.items():
            for child_name in child_names:
                self._global_class_hierarchies[base_name].append((child_name, file_path))

        if len(class_hierarchies) > 1:
            parallel_hierarchies = []
            for h1, h2 in combinations(class_hierarchies.values(), 2):
                if len(h1) > 1 and len(h2) > 1:
                    # Check for naming patterns
                    if any(c1.replace(h1[0], '') == c2.replace(h2[0], '')
                           for c1, c2 in product(h1, h2)):
                        # Check for method similarity
                        if (h1[0] in class_info and h2[0] in class_info and
                                (class_info[h1[0]] or class_info[h2[0]])):  # Ensure at least one set has methods
                            union_size = len(class_info[h1[0]] | class_info[h2[0]])
                            if union_size > 0:  # Prevent division by zero
                                similarity = len(class_info[h1[0]] & class_info[h2[0]]) / union_size
                                if similarity > 0.3:  # More than 30% similar methods
                                    parallel_hierarchies.extend([h1, h2])

            if parallel_hierarchies:
                self.add_smell(
                    name="Parallel Inheritance Hierarchies",
                    description=f"Parallel hierarchies detected: {' and '.join([' -> '.join(h) for h in parallel_hierarchies])} in {file_path}",
                    file_path=file_path,
                    module_class=None,
                    line_number=None,
                    severity='high'
                )

    def detect_shotgun_surgery(self, module, file_path):
        """
        Detect potential shotgun surgery in the given module.
        """
        method_calls = defaultdict(list)
        for node in module.body:
            for call in node.nodes_of_class(nodes.Call):
                if isinstance(call.func, nodes.Name):
                    # Skip common utility methods and logging
                    if call.func.name.lower() in {'log', 'print', 'str',
                                                  'len', 'isinstance', 'super'}:
                        continue

                    # Store both line number and context
                    context = None
                    for parent in call.node_ancestors():
                        if isinstance(parent, (nodes.FunctionDef, nodes.ClassDef)):
                            context = parent.name
                            break
                    method_calls[call.func.name].append((call.lineno, context))

        for method, calls in method_calls.items():
            unique_contexts = len(set(context for _, context in calls))
            if (len(calls) > self.thresholds["SHOTGUN_SURGERY_CALLS"] and
                    unique_contexts > self.thresholds["SHOTGUN_SURGERY_CONTEXTS"]):
                self.code_smells.append(CodeSmell(
                    name="Potential Shotgun Surgery",
                    description=f"Method '{method}' called in {unique_contexts} different contexts across {len(calls)} locations in {file_path}",
                    file_path=file_path,
                    module_class=method,
                    line_number=calls[0][0],
                    severity='high'
                ))

    def detect_comments(self, module, file_path):
        """
        Detect excessive comments in the given module and file.

        Args:
            module (astroid.Module): The AST module being analyzed
            file_path (str): Path to the file being analyzed
        """
        comment_blocks = []
        current_block = []
        code_lines = 0

        for i, line in enumerate(self.file_content):
            stripped_line = line.strip()
            if stripped_line.startswith('#'):
                current_block.append(i)
            else:
                if current_block:
                    comment_blocks.append(current_block)
                    current_block = []
                if stripped_line and not stripped_line.startswith('"""'):
                    code_lines += 1

        if current_block:
            comment_blocks.append(current_block)

        # Filter out license headers and module docstrings
        if comment_blocks and comment_blocks[0][0] == 0:
            comment_blocks.pop(0)

        # Calculate meaningful metrics
        comment_lines = sum(len(block) for block in comment_blocks)
        comment_ratio = comment_lines / max(code_lines, 1)
        large_comment_blocks = sum(1 for block in comment_blocks if len(block) > 5)

        if (comment_ratio > self.thresholds["EXCESSIVE_COMMENTS_RATIO"] and
                large_comment_blocks > self.thresholds["LARGE_COMMENT_BLOCKS"]):
            self.code_smells.append(CodeSmell(
                name="Excessive Comments",
                description=f"File has {comment_ratio:.1%} comment ratio with {large_comment_blocks} large comment blocks in {file_path}",
                file_path=file_path,
                module_class=None,
                line_number=None,
                severity='low'
            ))

    def detect_duplicate_code(self, module, file_path):
        """
        Detect duplicate code in the given module.
        """
        def normalize_code(node):
            """Normalize code by removing variable names and whitespace."""
            code = node.as_string()
            # Replace variable names with placeholders
            code = re.sub(r'\b[a-zA-Z_]\w*\b', 'VAR', code)
            # Remove whitespace and comments
            code = re.sub(r'\s+', '', code)
            code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
            return code

        code_blocks = defaultdict(list)
        for node in module.nodes_of_class(nodes.FunctionDef):
            # Skip small functions and test methods
            if (len(node.body) < self.thresholds["DUPLICATE_CODE_MIN_LINES"] or
                    node.name.startswith('test_')):
                continue

            # Skip simple getter/setter methods
            if len(node.body) == 1 and isinstance(node.body[0], (nodes.Return, nodes.Assign)):
                continue

            normalized_code = normalize_code(node)
            code_blocks[normalized_code].append((node.name, len(node.body)))

        for block, functions in code_blocks.items():
            if len(functions) >= self.thresholds["DUPLICATE_CODE_THRESHOLD"]:
                total_lines = sum(lines for _, lines in functions)
                self.code_smells.append(CodeSmell(
                    name="Duplicate Code",
                    description=f"Similar code found in functions: {', '.join(f[0] for f in functions)} ({total_lines} total lines) in {file_path}",
                    file_path=file_path,
                    module_class=', '.join(f[0] for f in functions),
                    line_number=None,
                    severity='high'
                ))

        # Accumulate for cross-file detection
        for normalized_code, functions in code_blocks.items():
            for func_name, num_lines in functions:
                self._global_code_blocks[normalized_code].append((func_name, file_path, num_lines))

    def detect_data_class(self, module, file_path):
        """
        Detect data classes in the given module.
        """
        for node in module.body:
            if isinstance(node, nodes.ClassDef):
                # Skip if it's already a dataclass or an exception
                if (any(decorator.name == 'dataclass' for decorator in node.decorators.nodes) if node.decorators else False or
                        any(base.name.endswith('Exception') for base in node.bases if isinstance(base, nodes.Name))):
                    continue

                methods = list(node.mymethods())

                # Skip empty classes or those with no methods
                if not methods:
                    continue

                # Count different types of methods
                getters = 0
                setters = 0
                others = 0

                for method in methods:
                    if method.name.startswith('__'):
                        continue  # Skip magic methods
                    elif method.name.startswith('get_') and len(method.body) == 1:
                        getters += 1
                    elif method.name.startswith('set_') and len(method.body) == 1:
                        setters += 1
                    else:
                        others += 1

                # Only flag if class is predominantly getters/setters
                if (others == 0 and getters + setters >= self.thresholds["DATA_CLASS_METHODS"] and
                        # Skip known data structures
                        not node.name.endswith(('DTO', 'Model', 'Entity', 'Record'))):
                    self.code_smells.append(CodeSmell(
                        name="Data Class",
                        description=f"Class '{node.name}' has {getters} getters and {setters} setters with no other methods in {file_path}",
                        file_path=file_path,
                        module_class=node.name,
                        line_number=node.lineno,
                        severity='medium'
                    ))

    def detect_dead_code(self, module, file_path):
        """
        Collect candidate dead functions for project-wide resolution.

        Per-file name matching alone cannot tell whether a function is consumed
        by another module, a test, an entry point, or the public API. Candidates
        are therefore deferred to _finalize_dead_code(), which consults the
        project-wide registry after every file has been parsed (Direction A).
        """
        for node in module.body:
            if not isinstance(node, nodes.FunctionDef):
                continue
            # Skip test functions and property methods
            if (node.name.startswith('test_') or
                    (node.decorators and any(
                        isinstance(d, nodes.Name) and d.name == 'property'
                        for d in node.decorators.nodes))):
                continue

            # Decorators suggesting public/external use (routes, API endpoints)
            public_decorator = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if any(name in str(decorator)
                           for name in ['api', 'route', 'endpoint', 'public', 'export']):
                        public_decorator = True
                        break

            # Exported via this module's __all__?
            exported = node.name in self._project_exports

            self._dead_candidates.append(
                (node.name, file_path, node.lineno, public_decorator, exported))

    def _finalize_dead_code(self):
        """Resolve candidate dead functions against the project-wide registry.

        A candidate is dead only when its name appears in no project reference,
        no import alias, and no ``__all__`` export. Confidence separates private
        unreferenced functions (high) from public names that may be part of an
        external API (low), instead of silently over-reporting (Direction A).
        """
        imported_names = set()
        for aliases in self._project_import_aliases.values():
            imported_names.update(aliases.keys())
        referenced = self._project_references | imported_names | self._project_exports

        # Group surviving candidates by file to preserve the per-file threshold
        by_file = defaultdict(list)
        for name, file_path, lineno, public_decorator, exported in self._dead_candidates:
            if public_decorator or exported or name in referenced:
                continue
            by_file[file_path].append((name, lineno))

        threshold = self.thresholds.get("DEAD_CODE_THRESHOLD", 3)
        for file_path, candidates in by_file.items():
            if len(candidates) < threshold:
                continue
            for name, lineno in candidates:
                confidence = ('high' if name.startswith('_')
                               else 'low (public name; may be external API)')
                self.add_smell(
                    name="Dead Code",
                    description=(
                        f"Potentially unused function '{name}' in {file_path} "
                        f"(no reference found in the analyzed project; "
                        f"confidence: {confidence})"
                    ),
                    file_path=file_path,
                    module_class=name,
                    line_number=lineno,
                    severity='low'
                )

    def detect_lazy_class(self, module, file_path):
        """
        Detect lazy classes in the given module.
        """
        for node in module.body:
            if isinstance(node, nodes.ClassDef):
                # Skip known valid small classes
                if (any(node.name.endswith(suffix) for suffix in
                    ['Exception', 'Error', 'Mixin', 'Interface', 'Abstract', 'Base']) or
                        (node.decorators and any(d.name == 'dataclass' for d in node.decorators.nodes))):
                    continue

                # Count non-trivial methods
                methods = []
                for method in node.mymethods():
                    # Skip magic methods and simple getters/setters
                    if (method.name.startswith('__') or
                            (len(method.body) == 1 and isinstance(method.body[0], (nodes.Return, nodes.Assign)))):
                        continue
                    methods.append(method)

                # Check complexity of methods
                total_lines = sum(m.tolineno - m.fromlineno for m in methods)
                if (len(methods) <= self.thresholds["LAZY_CLASS_METHODS"] and
                        total_lines <= self.thresholds["LAZY_CLASS_LINES"]):
                    self.code_smells.append(CodeSmell(
                        name="Lazy Class",
                        description=f"Class '{node.name}' has only {len(methods)} non-trivial methods with {total_lines} total lines in {file_path}",
                        file_path=file_path,
                        module_class=node.name,
                        line_number=node.lineno,
                        severity='low'
                    ))

    def detect_speculative_generality(self, module, file_path):
        """
        Detect speculative generality in the given module.
        """
        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip legitimate abstract base classes
            if (any(base.name.endswith('ABC') for base in node.bases if isinstance(base, nodes.Name)) or
                    node.name.endswith(('Interface', 'Base', 'Abstract'))):
                continue

            abstract_methods = []
            unused_params = []

            for method in node.mymethods():
                # Check for empty/pass methods
                if method.body and isinstance(method.body[0], nodes.Pass):
                    abstract_methods.append(method.name)

                # Check for unused parameters
                used_names = {n.name for n in method.nodes_of_class(nodes.Name)}
                param_names = {arg.name for arg in method.args.args if arg.name != 'self'}
                unused = param_names - used_names
                if unused:
                    unused_params.extend(unused)

            if (len(abstract_methods) >= self.thresholds["SPECULATIVE_GENERALITY_THRESHOLD"] or
                    len(unused_params) >= self.thresholds["UNUSED_PARAMETERS_THRESHOLD"]):
                description = []
                if abstract_methods:
                    description.append(
                        f"has {len(abstract_methods)} empty methods: {', '.join(abstract_methods)}")
                if unused_params:
                    description.append(
                        f"has {len(unused_params)} unused parameters: {', '.join(unused_params)}")

                self.code_smells.append(CodeSmell(
                    name="Speculative Generality",
                    description=f"Class '{node.name}' {' and '.join(description)} in {file_path}",
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno,
                    severity='medium'
                ))

    def detect_feature_envy(self, module, file_path):
        """
        Detect feature envy in the given module.
        """
        for node in module.nodes_of_class(nodes.FunctionDef):
            # Skip property methods and simple delegators
            is_property = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if isinstance(decorator, nodes.Name) and decorator.name == 'property':
                        is_property = True
                        break
                    elif isinstance(decorator, nodes.Call):
                        if isinstance(decorator.func,
                                      nodes.Name) and decorator.func.name == 'property':
                            is_property = True
                            break
                    elif isinstance(decorator, nodes.Attribute):
                        if decorator.attrname == 'property':
                            is_property = True
                            break

            if (is_property or
                    len(node.body) == 1 and isinstance(node.body[0], nodes.Return)):
                continue

            # Resolve receiver bindings inside this method (Direction A):
            # `other = RHS` tells us what `other` actually refers to, so a
            # receiver bound to self.* or a local utility is not envy.
            local_bindings = {}
            for assign in node.nodes_of_class(nodes.Assign):
                for target in assign.targets:
                    if not isinstance(target, nodes.AssignName):
                        continue
                    value = assign.value
                    if isinstance(value, nodes.Name):
                        local_bindings[target.name] = value.name
                    elif (isinstance(value, nodes.Attribute)
                          and isinstance(value.expr, nodes.Name)
                          and value.expr.name == 'self'):
                        # `other = self.data` → receiver derives from self
                        local_bindings[target.name] = 'self'

            # Track method calls by class
            class_calls = defaultdict(int)
            local_calls = 0

            for sub_node in node.nodes_of_class(nodes.Attribute):
                if isinstance(sub_node.expr, nodes.Name):
                    receiver = sub_node.expr.name
                    if receiver == 'self':
                        local_calls += 1
                        continue
                    # Skip common utility objects
                    if receiver.lower() in {'logger', 'config', 'utils', 'helper'}:
                        continue
                    # Receiver bound to self.* or a local utility → not envy
                    bound = local_bindings.get(receiver)
                    if bound is not None and (
                            bound == 'self' or
                            bound.lower() in {'logger', 'config', 'utils', 'helper'}):
                        continue
                    class_calls[receiver] += 1

            if class_calls:
                max_calls = max(class_calls.values())
                max_class = max(class_calls.items(), key=lambda x: x[1])[0]

                # Check if external calls significantly outnumber local calls
                if (max_calls > self.thresholds["FEATURE_ENVY_CALLS"] and
                        max_calls > local_calls * 2):  # At least twice as many external calls
                    # Confidence: resolved when the receiver names a project-defined
                    # class or an imported alias; unresolved otherwise (free variable
                    # that may refer to an external object) (Direction A).
                    resolved = (
                        max_class in self._all_defined_names() or
                        any(max_class in aliases
                            for aliases in self._project_import_aliases.values())
                    )
                    confidence = 'resolved' if resolved else 'unresolved receiver (possible external object)'
                    self.add_smell(
                        name="Feature Envy",
                        description=(
                            f"Method '{node.name}' makes {max_calls} calls to "
                            f"'{max_class}' but only {local_calls} local calls in "
                            f"{file_path} [confidence: {confidence}]"
                        ),
                        file_path=file_path,
                        module_class=node.name,
                        line_number=node.lineno,
                        severity='medium'
                    )

    def detect_inappropriate_intimacy(self, module, file_path):
        """
        Detect inappropriate intimacy in the given module.
        """
        class_fields = defaultdict(set)
        class_methods = defaultdict(set)
        class_relationships = defaultdict(set)  # Track inheritance and composition

        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip data classes and utility classes
            is_dataclass = False
            if node.decorators:
                for decorator in node.decorators.nodes:
                    if isinstance(decorator, nodes.Name) and decorator.name == 'dataclass':
                        is_dataclass = True
                        break
                    elif isinstance(decorator, nodes.Call):
                        if isinstance(decorator.func,
                                      nodes.Name) and decorator.func.name == 'dataclass':
                            is_dataclass = True
                            break
                    elif isinstance(decorator, nodes.Attribute):
                        if decorator.attrname == 'dataclass':
                            is_dataclass = True
                            break

            if (is_dataclass or node.name.endswith(('Utils', 'Helper', 'Factory'))):
                continue

            # Store class methods and fields
            class_methods[node.name] = {
                n.name for n in node.mymethods()
                if not n.name.startswith('__')  # Skip magic methods
            }
            class_fields[node.name] = {
                name for name in node.instance_attrs.keys()
                if not name.startswith('_')  # Skip private fields
            }

            # Track inheritance relationships
            for base in node.bases:
                if isinstance(base, nodes.Name):
                    class_relationships[node.name].add(base.name)

            # Track composition through instance variables
            for field in node.instance_attrs.values():
                if isinstance(field, nodes.AssignAttr) and isinstance(field.expr, nodes.Name):
                    class_relationships[node.name].add(field.expr.name)

        # Accumulate for cross-file detection
        for class_name in class_methods:
            key = f"{file_path}::{class_name}"
            self._global_class_info[key] = {
                "fields": class_fields[class_name],
                "methods": class_methods[class_name],
                "relationships": class_relationships[class_name],
                "class_name": class_name,
                "file_path": file_path,
            }

        for class_name, methods in class_methods.items():
            for other_class, other_fields in class_fields.items():
                if class_name != other_class:
                    # Skip if there's a valid relationship
                    if (other_class in class_relationships[class_name] or
                            class_name in class_relationships[other_class]):
                        continue

                    shared = len(methods.intersection(other_fields))
                    method_ratio = shared / len(methods) if methods else 0

                    if (shared > self.thresholds["INAPPROPRIATE_INTIMACY_SHARED"] and
                            method_ratio > 0.3):  # More than 30% of methods are shared
                        self.add_smell(
                            name="Inappropriate Intimacy",
                            description=f"Class '{class_name}' might be too intimate with '{other_class}' "
                            f"({shared} shared members, {method_ratio:.1%} of methods) in {file_path}",
                            file_path=file_path,
                            module_class=class_name,
                            line_number=None,
                            severity='medium'
                        )

    def detect_message_chains(self, module, file_path):
        """
        Detect message chains in the given module.
        """
        def get_chain_length(node):
            length = 0
            chain = []
            current = node
            while isinstance(current, nodes.Attribute):
                length += 1
                chain.append(current.attrname)
                current = current.expr
            return length, chain

        def is_builder_pattern(chain):
            """Check if the chain follows builder pattern."""
            return all(name.startswith(('set_', 'with_', 'add_')) for name in chain)

        def is_common_pattern(chain):
            """Check if the chain is a common valid pattern."""
            common_patterns = {
                'logging': {'debug', 'info', 'warning', 'error', 'critical'},
                'paths': {'parent', 'name', 'suffix', 'stem'},
                'testing': {'assert_', 'expect', 'mock'},
                'db': {'query', 'filter', 'order_by', 'limit', 'all', 'first'}
            }
            return any(any(method in pattern for method in chain)
                       for pattern in common_patterns.values())

        for node in module.nodes_of_class(nodes.Attribute):
            chain_length, chain = get_chain_length(node)

            # Skip if it's a valid pattern
            if (chain_length <= self.thresholds["MESSAGE_CHAIN_LENGTH"] or
                is_builder_pattern(chain) or
                    is_common_pattern(chain)):
                continue

            # Get context for better description
            context = None
            for parent in node.node_ancestors():
                if isinstance(parent, (nodes.FunctionDef, nodes.ClassDef)):
                    context = parent.name
                    break

            self.code_smells.append(CodeSmell(
                name="Message Chains",
                description=f"Long chain ({chain_length} calls: {' -> '.join(reversed(chain))}) "
                f"in {context or 'unknown context'} at line {node.lineno} in {file_path}",
                file_path=file_path,
                module_class=context,
                line_number=node.lineno,
                severity='medium'
            ))

    def detect_middle_man(self, module, file_path):
        """
        Detect middle man classes in the given module.
        """
        for node in module.nodes_of_class(nodes.ClassDef):
            # Skip known patterns and small classes
            if (node.name.endswith(('Proxy', 'Delegate', 'Adapter', 'Facade')) or
                    len(node.body) <= 3):  # Very small classes might be intentional adapters
                continue

            methods = list(node.mymethods())
            total_methods = len(methods)

            if total_methods == 0:
                continue

            delegating_methods = 0
            delegate_targets = defaultdict(list)

            for method in methods:
                # Skip property methods and magic methods
                is_property = False
                if method.decorators:
                    for decorator in method.decorators.nodes:
                        if isinstance(decorator, nodes.Name) and decorator.name == 'property':
                            is_property = True
                            break
                        elif isinstance(decorator, nodes.Call):
                            if isinstance(decorator.func,
                                          nodes.Name) and decorator.func.name == 'property':
                                is_property = True
                                break
                        elif isinstance(decorator, nodes.Attribute):
                            if decorator.attrname == 'property':
                                is_property = True
                                break

                if is_property or method.name.startswith('__'):
                    continue

                # Check if method is just delegating
                if len(method.body) == 1 and isinstance(method.body[0], nodes.Return):
                    return_value = method.body[0].value
                    if isinstance(return_value, nodes.Call):
                        delegating_methods += 1
                        # Track which object we're delegating to
                        if isinstance(return_value.func, nodes.Attribute):
                            delegate_targets[return_value.func.expr.as_string()].append(method.name)

            delegation_ratio = delegating_methods / total_methods if total_methods > 0 else 0
            if (delegation_ratio > self.thresholds["MIDDLE_MAN_RATIO"] and
                    len(delegate_targets) <= 2):  # Only flag if delegating to 1-2 objects
                primary_delegate = max(delegate_targets.items(), key=lambda x: len(x[1]))
                self.add_smell(
                    name="Middle Man",
                    description=f"Class '{node.name}' delegates {delegating_methods}/{total_methods} methods "
                    f"({delegation_ratio:.1%}), mainly to {primary_delegate[0]} in {file_path}",
                    file_path=file_path,
                    module_class=node.name,
                    line_number=node.lineno,
                    severity='medium'
                )

    def detect_cross_file_smells(self):
        """
        Detect smells requiring cross-file context.
        Call this once after all per-file detect_smells() calls are complete.
        """
        self._finalize_dead_code()
        self._cross_file_alternative_classes()
        self._cross_file_data_clumps()
        self._cross_file_duplicate_code()
        self._cross_file_inappropriate_intimacy()
        self._cross_file_parallel_inheritance()

    def _cross_file_alternative_classes(self):
        for methods, entries in self._global_class_methods.items():
            if len(methods) < 2:
                continue
            files_seen = {fp for _, fp in entries}
            if len(files_seen) < 2:
                continue
            if len(entries) >= self.thresholds["ALTERNATIVE_CLASSES_THRESHOLD"]:
                class_list = [f"{cls} ({fp})" for cls, fp in entries]
                self.add_smell(
                    name="Alternative Classes with Different Interfaces",
                    description=f"Classes {', '.join(class_list)} share similar methods {', '.join(methods)} across files",
                    file_path=", ".join(files_seen),
                    module_class=", ".join(cls for cls, _ in entries),
                    line_number=None,
                    severity='medium'
                )

    def _cross_file_data_clumps(self):
        for params, entries in self._global_param_groups.items():
            if len(params) < self.thresholds["DATA_CLUMPS_THRESHOLD"]:
                continue
            files_seen = {fp for _, fp in entries}
            if len(files_seen) < 2:
                continue
            if len(entries) > 1:
                func_list = [f"{fn} ({fp})" for fn, fp in entries]
                self.add_smell(
                    name="Data Clumps",
                    description=f"Parameters {', '.join(params)} appear together across files in: {', '.join(func_list)}",
                    file_path=", ".join(files_seen),
                    module_class=", ".join(fn for fn, _ in entries),
                    line_number=None,
                    severity='medium'
                )

    def _cross_file_duplicate_code(self):
        for normalized_code, entries in self._global_code_blocks.items():
            files_seen = {fp for _, fp, _ in entries}
            if len(files_seen) < 2:
                continue
            if len(entries) >= self.thresholds["DUPLICATE_CODE_THRESHOLD"]:
                total_lines = sum(nl for _, _, nl in entries)
                func_list = [f"{fn} ({fp})" for fn, fp, _ in entries]
                self.add_smell(
                    name="Duplicate Code",
                    description=f"Similar code found across files in functions: {', '.join(func_list)} ({total_lines} total lines)",
                    file_path=", ".join(files_seen),
                    module_class=", ".join(fn for fn, _, _ in entries),
                    line_number=None,
                    severity='high'
                )

    def _cross_file_inappropriate_intimacy(self):
        entries = list(self._global_class_info.values())
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                if a["file_path"] == b["file_path"]:
                    continue
                if (b["class_name"] in a["relationships"] or
                        a["class_name"] in b["relationships"]):
                    continue
                shared = len(a["methods"].intersection(b["fields"]))
                method_ratio = shared / len(a["methods"]) if a["methods"] else 0
                if (shared > self.thresholds["INAPPROPRIATE_INTIMACY_SHARED"] and
                        method_ratio > 0.3):
                    self.add_smell(
                        name="Inappropriate Intimacy",
                        description=(
                            f"Class '{a['class_name']}' ({a['file_path']}) might be too intimate "
                            f"with '{b['class_name']}' ({b['file_path']}) "
                            f"({shared} shared members, {method_ratio:.1%} of methods)"
                        ),
                        file_path=a["file_path"],
                        module_class=a["class_name"],
                        line_number=None,
                        severity='medium'
                    )

    def _cross_file_parallel_inheritance(self):
        class_info = {}
        for key, info in self._global_class_info.items():
            class_info[info["class_name"]] = info.get("methods", set())

        hierarchies = {
            base: [child for child, _ in children]
            for base, children in self._global_class_hierarchies.items()
        }
        hierarchy_files = {
            base: {fp for _, fp in children}
            for base, children in self._global_class_hierarchies.items()
        }

        if len(hierarchies) <= 1:
            return

        for (b1, h1), (b2, h2) in combinations(hierarchies.items(), 2):
            all_files = hierarchy_files[b1] | hierarchy_files[b2]
            if len(all_files) < 2:
                continue
            if len(h1) > 1 and len(h2) > 1:
                if any(c1.replace(h1[0], '') == c2.replace(h2[0], '')
                       for c1, c2 in product(h1, h2)):
                    if h1[0] in class_info and h2[0] in class_info:
                        union_size = len(class_info[h1[0]] | class_info[h2[0]])
                        if union_size > 0:
                            similarity = len(class_info[h1[0]] & class_info[h2[0]]) / union_size
                            if similarity > 0.3:
                                self.add_smell(
                                    name="Parallel Inheritance Hierarchies",
                                    description=(
                                        f"Parallel cross-file hierarchies: "
                                        f"{' -> '.join(h1)} and {' -> '.join(h2)}"
                                    ),
                                    file_path=", ".join(all_files),
                                    module_class=None,
                                    line_number=None,
                                    severity='high'
                                )

    def print_report(self):
        """
        Print a report of all detected code smells.

        If no code smells are detected, it prints a message indicating so.
        """
        if not self.code_smells:
            print("No code smells detected.")
        else:
            print("Detected Code Smells:")
            for smell in self.code_smells:
                print(f"- {smell.name}: {smell.description}")

    # ------------------------------------------------------------------
    # Magic literals and constant conditions
    # ------------------------------------------------------------------

    # Numbers that are meaningful by themselves and therefore not "magic".
    MAGIC_ALLOWED_NUMBERS = frozenset({-1, 0, 1, 2})

    # Language-protocol names that look like literals but are part of the
    # Python object model rather than domain vocabulary.
    MAGIC_STRING_IGNORED = frozenset({
        'self', 'cls', '__init__', '__main__', '__all__', '__name__',
    })

    # Comparison operators usable to evaluate a literal-only condition.
    _CONDITION_OPERATORS = {
        '==': operator.eq,
        '!=': operator.ne,
        '<': operator.lt,
        '<=': operator.le,
        '>': operator.gt,
        '>=': operator.ge,
        'in': lambda left, right: left in right,
        'not in': lambda left, right: left not in right,
        'is': operator.is_,
        'is not': operator.is_not,
    }

    @staticmethod
    def _is_function_node(node):
        return isinstance(node, (nodes.FunctionDef, nodes.AsyncFunctionDef))

    def _iter_scope_functions(self, module):
        """
        Yield module-level functions and methods, but not functions nested
        inside other functions (those are not independently addressable).
        """
        for node in module.body:
            if self._is_function_node(node):
                yield node
            elif isinstance(node, nodes.ClassDef):
                for child in node.body:
                    if self._is_function_node(child):
                        yield child

    def _walk_own_scope(self, function):
        """
        Yield nodes inside a function body, stopping at nested scopes so that
        nested functions are not attributed to the enclosing function twice.
        """
        stack = list(function.body)
        while stack:
            node = stack.pop()
            yield node
            if self._is_function_node(node) or isinstance(node, (nodes.Lambda, nodes.ClassDef)):
                continue
            stack.extend(node.get_children())

    def _named_constant_values(self, module):
        """Collect values bound to module-level UPPER_CASE constants."""
        values = set()
        for node in module.body:
            if isinstance(node, nodes.Assign) and isinstance(node.value, nodes.Const):
                for target in node.targets:
                    name = getattr(target, 'name', None)
                    if isinstance(name, str) and name.isupper():
                        values.add(node.value.value)
        return values

    @staticmethod
    def _is_docstring(node):
        """A bare string statement is documentation, not a magic literal."""
        parent = node.parent
        if not isinstance(parent, nodes.Expr):
            return False
        scope = parent.parent
        body = getattr(scope, 'body', None)
        return bool(body) and body[0] is parent

    @staticmethod
    def _string_literals(node):
        """Return string Const nodes directly held by an operand."""
        if isinstance(node, nodes.Const) and isinstance(node.value, str):
            return [node]
        if isinstance(node, (nodes.Tuple, nodes.List, nodes.Set)):
            return [elt for elt in node.elts
                    if isinstance(elt, nodes.Const) and isinstance(elt.value, str)]
        return []

    @staticmethod
    def _is_magic_string(value):
        """Filter trivial or protocol strings out of Magic String candidates."""
        stripped = value.strip()
        if len(stripped) < 2:
            return False
        return stripped not in CodeSmellDetector.MAGIC_STRING_IGNORED

    def _source_line(self, lineno):
        content = getattr(self, 'file_content', [])
        if 1 <= lineno <= len(content):
            return content[lineno - 1].strip()[:80]
        return ""

    def detect_magic_numbers(self, module, file_path):
        """
        Detect functions that hard-code numeric literals instead of naming them.

        Literals in {-1, 0, 1, 2} and values bound to module-level UPPER_CASE
        constants are not reported, so the detector targets unexplained
        domain values rather than ordinary arithmetic.
        """
        threshold = self.thresholds.get('MAGIC_NUMBER_THRESHOLD', 2)
        named_values = self._named_constant_values(module)

        for function in self._iter_scope_functions(module):
            hits = defaultdict(list)

            for node in self._walk_own_scope(function):
                if not isinstance(node, nodes.Const):
                    continue
                value = node.value
                # bool is a subclass of int; True/False are not magic numbers
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if value in self.MAGIC_ALLOWED_NUMBERS or value in named_values:
                    continue
                hits[value].append(node.lineno)

            if len(hits) < threshold:
                continue

            listing = ", ".join(
                f"{value} (line {min(lines)})" for value, lines in sorted(hits.items())
            )
            severity = 'High' if len(hits) >= threshold * 2 else 'Medium'
            self.add_smell(
                "Magic Number",
                f"Function '{function.name}' uses {len(hits)} distinct magic numbers: {listing}",
                file_path,
                function.name,
                min(min(lines) for lines in hits.values()),
                severity=severity
            )

    def detect_magic_strings(self, module, file_path):
        """
        Detect string literals used in comparisons or repeated within a function.

        A single literal comparison is tolerated until MAGIC_STRING_THRESHOLD
        distinct literals accumulate, which keeps the signal focused on
        functions encoding domain vocabularies as inline strings.
        """
        threshold = self.thresholds.get('MAGIC_STRING_THRESHOLD', 2)
        repeat_threshold = self.thresholds.get('MAGIC_STRING_OCCURRENCES', 2)

        for function in self._iter_scope_functions(module):
            counts = defaultdict(list)
            compared = {}

            for node in self._walk_own_scope(function):
                if isinstance(node, nodes.Compare):
                    # `is` comparisons are identity checks, not vocabulary
                    operands = [node.left] + [
                        operand for op_name, operand in node.ops
                        if op_name not in ('is', 'is not')
                    ]
                    for operand in operands:
                        for const in self._string_literals(operand):
                            if self._is_magic_string(const.value):
                                compared.setdefault(const.value, const.lineno)
                elif isinstance(node, nodes.Const) and isinstance(node.value, str):
                    if self._is_docstring(node) or isinstance(node.parent, nodes.JoinedStr):
                        continue
                    # Strings used as subscript keys are internal dict keys,
                    # not a domain vocabulary worth naming.
                    if isinstance(node.parent, nodes.Subscript):
                        continue
                    if self._is_magic_string(node.value):
                        counts[node.value.strip()].append(node.lineno)

            flagged = {value: lineno for value, lineno in compared.items() if value.strip()}
            for value, lines in counts.items():
                if len(lines) >= repeat_threshold:
                    flagged.setdefault(value, lines[0])

            if len(flagged) < threshold:
                continue

            listing = ", ".join(
                f"'{value}' (line {lineno})"
                for value, lineno in sorted(flagged.items(), key=lambda item: item[1])
            )
            self.add_smell(
                "Magic String",
                f"Function '{function.name}' has {len(flagged)} magic strings "
                f"in comparisons or repeated literals: {listing}",
                file_path,
                function.name,
                min(flagged.values()),
                severity='Medium'
            )

    def _collect_constant_vars(self, function):
        """
        Find local variables assigned exactly one literal value and never
        reassigned, so a later condition on them is a constant condition.
        """
        assigned = defaultdict(list)
        mutated = set()

        for node in self._walk_own_scope(function):
            if isinstance(node, nodes.Assign):
                value_node = node.value if isinstance(node.value, nodes.Const) else None
                for target in node.targets:
                    if isinstance(target, nodes.AssignName):
                        assigned[target.name].append((value_node, node.lineno))
            elif isinstance(node, nodes.AnnAssign) and node.value is not None:
                if isinstance(node.target, nodes.AssignName):
                    value_node = node.value if isinstance(node.value, nodes.Const) else None
                    assigned[node.target.name].append((value_node, node.lineno))
            elif isinstance(node, nodes.AugAssign):
                if isinstance(node.target, nodes.AssignName):
                    mutated.add(node.target.name)
            elif isinstance(node, (nodes.For, nodes.AsyncFor)):
                targets = []
                if isinstance(node.target, nodes.AssignName):
                    targets = [node.target]
                elif isinstance(node.target, nodes.Tuple):
                    targets = [elt for elt in node.target.elts
                               if isinstance(elt, nodes.AssignName)]
                mutated.update(target.name for target in targets)

        const_vars = {}
        for name, records in assigned.items():
            if name in mutated or len(records) != 1:
                continue
            value_node, lineno = records[0]
            if value_node is None:
                continue
            const_vars[name] = (value_node.value, lineno)
        return const_vars

    @staticmethod
    def _resolve_literal(node, const_vars):
        """
        Resolve an operand to a literal value.

        Returns:
            tuple or None: (value, human readable origin) when resolvable.
        """
        if isinstance(node, nodes.Const):
            return node.value, None
        if isinstance(node, nodes.Name) and node.name in const_vars:
            value, lineno = const_vars[node.name]
            return value, f"'{node.name}' is assigned the literal {value!r} at line {lineno}"
        return None

    def _constant_test(self, test, const_vars):
        """
        Decide whether a condition is decidable at analysis time.

        Returns:
            tuple or None: (always_true, reason) when decidable.
        """
        if isinstance(test, nodes.Const):
            return bool(test.value), "the condition is a literal"

        if isinstance(test, nodes.Name) and test.name in const_vars:
            value, lineno = const_vars[test.name]
            return bool(value), f"'{test.name}' is assigned the literal {value!r} at line {lineno}"

        if isinstance(test, nodes.Compare) and len(test.ops) == 1:
            op_name, right_node = test.ops[0]
            left = self._resolve_literal(test.left, const_vars)
            right = self._resolve_literal(right_node, const_vars)
            if left is None or right is None:
                return None
            compare = self._CONDITION_OPERATORS.get(op_name)
            if compare is None:
                return None
            try:
                result = bool(compare(left[0], right[0]))
            except (TypeError, ValueError):
                return None
            reasons = [reason for reason in (left[1], right[1]) if reason]
            return result, "; ".join(reasons) or "both operands are literals"

        return None

    def detect_constant_conditions(self, module, file_path):
        """
        Detect if/while conditions that can never change branch: literal
        conditions, literal-only comparisons, and comparisons against a
        variable that is assigned one literal value.
        """
        for function in self._iter_scope_functions(module):
            const_vars = self._collect_constant_vars(function)

            for node in self._walk_own_scope(function):
                if not isinstance(node, (nodes.If, nodes.While)):
                    continue
                # `while True:` is an intentional loop idiom, not a bug
                if (isinstance(node, nodes.While) and isinstance(node.test, nodes.Const)
                        and bool(node.test.value)):
                    continue

                verdict = self._constant_test(node.test, const_vars)
                if verdict is None:
                    continue

                always_true, reason = verdict
                snippet = self._source_line(node.lineno)
                description = (
                    f"Condition at line {node.lineno} always evaluates to {always_true} "
                    f"({reason})"
                )
                if snippet:
                    description += f": {snippet}"

                self.add_smell(
                    "Constant Condition",
                    description,
                    file_path,
                    function.name,
                    node.lineno,
                    # an always-false guard hides dead code, so raise it
                    severity='High' if not always_true else 'Medium'
                )

    def add_smell(self, name, description, file_path, module_class,
                  line_number=None, severity='medium'):
        """
        Add a detected smell to the list of code smells.

        Args:
            name (str): The name of the smell
            description (str): Description of the smell
            file_path (str): Path to the file containing the smell
            module_class (str): The module or class containing the smell
            line_number (int, optional): The line number where the smell was detected
            severity (str, optional): The severity level of the smell (default: 'medium')
        """
        self.code_smells.append(CodeSmell(
            name=name,
            description=description,
            file_path=file_path,
            module_class=module_class,
            line_number=line_number,
            severity=severity
        ))
