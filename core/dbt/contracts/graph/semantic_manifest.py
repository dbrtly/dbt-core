from dbt_semantic_interfaces.implementations.metric import PydanticMetric
from dbt_semantic_interfaces.implementations.project_configuration import (
    PydanticProjectConfiguration,
)
from dbt_semantic_interfaces.implementations.semantic_manifest import PydanticSemanticManifest
from dbt_semantic_interfaces.implementations.semantic_model import PydanticSemanticModel
from dbt_semantic_interfaces.implementations.time_spine_table_configuration import (
    PydanticTimeSpineTableConfiguration,
)
from dbt_semantic_interfaces.type_enums import TimeGranularity

from dbt.clients.system import write_file
from dbt.exceptions import ParsingError


class SemanticManifest:
    def __init__(self, manifest):
        self.manifest = manifest

    def write_json_to_file(self, file_path: str):
        semantic_manifest = self._get_pydantic_semantic_manifest()
        json = semantic_manifest.json()
        write_file(file_path, json)

    def _get_pydantic_semantic_manifest(self) -> PydanticSemanticManifest:
        project_config = PydanticProjectConfiguration(
            time_spine_table_configurations=[],
        )
        pydantic_semantic_manifest = PydanticSemanticManifest(
            metrics=[], semantic_models=[], project_configuration=project_config
        )

        for semantic_model in self.manifest.semantic_models.values():
            pydantic_semantic_manifest.semantic_models.append(
                PydanticSemanticModel.parse_obj(semantic_model.to_dict())
            )

        for metric in self.manifest.metrics.values():
            pydantic_semantic_manifest.metrics.append(PydanticMetric.parse_obj(metric.to_dict()))

        # Look for time-spine table model and create time spine table configuration
        if self.manifest.semantic_models:
            # Get model for time_spine_table
            time_spine_model_name = "metricflow_time_spine"
            model = self.manifest.ref_lookup.find(time_spine_model_name, None, None, self.manifest)
            if not model:
                raise ParsingError(
                    "The semantic layer requires a 'metricflow_time_spine' model in the project, but none was found. "
                    "Guidance on creating this model can be found on our docs site ("
                    "https://docs.getdbt.com/docs/build/metricflow-time-spine) "
                )
            # Create time_spine_table_config, set it in project_config, and add to semantic manifest
            time_spine_table_config = PydanticTimeSpineTableConfiguration(
                location=model.relation_name,
                column_name="date_day",
                grain=TimeGranularity.DAY,
            )
            pydantic_semantic_manifest.project_configuration.time_spine_table_configurations = [
                time_spine_table_config
            ]

        return pydantic_semantic_manifest
