//! SchemaComplianceReward — binary reward from JSON Schema validation.

use crate::reward::RewardFn;
use crate::trajectory::Step;

/// Scores 1.0 if the step's action validates against a JSON Schema, penalty otherwise.
#[derive(Debug)]
pub struct SchemaComplianceReward {
    schema: serde_json::Value,
    reward: f64,
    penalty: f64,
}

impl SchemaComplianceReward {
    pub fn new(schema: serde_json::Value, reward: f64, penalty: f64) -> Self {
        Self {
            schema,
            reward,
            penalty,
        }
    }
}

impl RewardFn for SchemaComplianceReward {
    fn name(&self) -> &str {
        "schema_compliance"
    }

    fn score(&self, step: &Step) -> f64 {
        let action_value = serde_json::to_value(&step.action).unwrap_or_default();
        if jsonschema::is_valid(&self.schema, &action_value) {
            self.reward
        } else {
            self.penalty
        }
    }
}
