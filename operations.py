import math
from abc import ABC, abstractmethod
from typing import Mapping


class Operation(ABC):
    @abstractmethod
    def calculate(self, a: float, b: float) -> float:
        raise NotImplementedError


class Add(Operation):
    def calculate(self, a: float, b: float) -> float:
        return a + b


class Subtract(Operation):
    def calculate(self, a: float, b: float) -> float:
        return a - b


class Multiply(Operation):
    def calculate(self, a: float, b: float) -> float:
        return a * b


class Divide(Operation):
    def calculate(self, a: float, b: float) -> float:
        if b == 0:
            raise ValueError("Cannot divide by zero")
        return a / b


class Calculator:
    def __init__(self, operations: Mapping[str, Operation]):
        self._operations = dict(operations)

    def supports(self, path):
        return path in self._operations

    def calculate(self, path, a, b):
        if not math.isfinite(a) or not math.isfinite(b):
            raise ValueError("Invalid number")
        result = self._operations[path].calculate(a, b)
        if not math.isfinite(result):
            raise ValueError("Result is too large")
        return format(result, ".15g") if result else "0"
