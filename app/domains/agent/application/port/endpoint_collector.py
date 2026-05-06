from abc import ABC, abstractmethod

from app.domains.agent.domain.entity.api_endpoint import ApiEndpoint


class EndpointCollector(ABC):
    @abstractmethod
    def collect(self) -> list[ApiEndpoint]:
        pass
