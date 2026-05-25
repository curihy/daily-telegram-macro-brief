from __future__ import annotations

from abc import ABC, abstractmethod


class BaseAgent(ABC):
    name: str

    @abstractmethod
    def run(self):
        raise NotImplementedError
