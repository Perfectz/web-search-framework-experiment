from __future__ import annotations

from abc import ABC, abstractmethod

from apartment_agent.models import Listing, SearchCriteria, SearchSource


class BaseAdapter(ABC):
    @abstractmethod
    def collect(
        self,
        source: SearchSource,
        criteria: SearchCriteria,
        browser_capture: object | None = None,
    ) -> list[Listing]:
        raise NotImplementedError

