"""SchemaComplianceReward — binary reward from JSON Schema validation."""

from __future__ import annotations

from typing import Any

import jsonschema

from jeeves_airframe.trajectory.types import Step


class SchemaComplianceReward:
    """Scores 1.0 if the step's action output validates against a JSON Schema, penalty otherwise.

    The schema is typically the output_schema from the pipeline stage config.
    """

    def __init__(self, schema: dict[str, Any], *, reward: float = 1.0, penalty: float = -1.0):
        self._schema = schema
        self._reward = reward
        self._penalty = penalty
        jsonschema.Draft7Validator.check_schema(schema)

    @property
    def name(self) -> str:
        return "schema_compliance"

    def score(self, step: Step) -> float:
        try:
            jsonschema.validate(instance=step.action, schema=self._schema)
            return self._reward
        except jsonschema.ValidationError:
            return self._penalty
