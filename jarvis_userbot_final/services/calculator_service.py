
import ast
import math
import operator
from dataclasses import dataclass

class CalculatorError(ValueError):
    pass

@dataclass
class Calculation:
    expression: str
    normalized: str
    result: str

class SafeCalculator:
    MAX_LENGTH = 200
    MAX_ABS = 10**100

    BINOPS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
    }
    UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
    FUNCS = {
        "sqrt": math.sqrt,
        "abs": abs,
        "round": round,
        "floor": math.floor,
        "ceil": math.ceil,
    }
    CONSTANTS = {"pi": math.pi, "e": math.e}

    def normalize(self, expression: str) -> str:
        expression = expression.strip()
        if not expression:
            raise CalculatorError("Expression is empty.")
        if len(expression) > self.MAX_LENGTH:
            raise CalculatorError("Expression is too long.")
        expression = expression.replace("^", "**").replace("×", "*").replace("÷", "/")
        # A trailing percent means "percentage of 100".
        if expression.endswith("%"):
            base = expression[:-1].strip()
            if not base:
                raise CalculatorError("Invalid percentage.")
            expression = f"({base})/100"
        return expression

    def calculate(self, expression: str) -> Calculation:
        normalized = self.normalize(expression)
        try:
            node = ast.parse(normalized, mode="eval")
        except SyntaxError as exc:
            raise CalculatorError("I could not understand this expression.") from exc
        value = self._eval(node.body)
        if isinstance(value, complex) or not math.isfinite(float(value)):
            raise CalculatorError("Result is not a finite real number.")
        if abs(value) > self.MAX_ABS:
            raise CalculatorError("Result is too large.")
        result = str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
        return Calculation(expression, normalized, result)

    def _eval(self, node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise CalculatorError("Only numbers are allowed.")
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self.BINOPS:
            left = self._eval(node.left)
            right = self._eval(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 1000:
                raise CalculatorError("Exponent is too large.")
            try:
                return self.BINOPS[type(node.op)](left, right)
            except (ArithmeticError, OverflowError, ValueError, ZeroDivisionError) as exc:
                raise CalculatorError(str(exc) or "Calculation failed.") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in self.UNARY:
            return self.UNARY[type(node.op)](self._eval(node.operand))
        if isinstance(node, ast.Name) and node.id in self.CONSTANTS:
            return self.CONSTANTS[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in self.FUNCS:
            if len(node.args) not in (1, 2):
                raise CalculatorError("Invalid function arguments.")
            args = [self._eval(a) for a in node.args]
            try:
                return self.FUNCS[node.func.id](*args)
            except (ArithmeticError, ValueError, TypeError) as exc:
                raise CalculatorError(str(exc) or "Function failed.") from exc
        raise CalculatorError("Bu ifodada qo‘llab-quvvatlanmaydigan amal bor.")
