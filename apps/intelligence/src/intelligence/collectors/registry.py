from intelligence.collectors.base import Collector
from intelligence.collectors.data_gov_my import DataGovMyDatasetCollector

COLLECTOR_REGISTRY: dict[str, type[Collector]] = {
    "data_gov_my_dataset": DataGovMyDatasetCollector,
}


def get_collector_class(name: str) -> type[Collector]:
    try:
        return COLLECTOR_REGISTRY[name]
    except KeyError:
        registered = ", ".join(sorted(COLLECTOR_REGISTRY)) or "(none)"
        raise ValueError(f"No collector registered for '{name}'. Registered: {registered}") from None
