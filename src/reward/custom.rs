//! CallableRewardFn — wraps a closure as a RewardFn.

use crate::reward::RewardFn;
use crate::trajectory::Step;

/// Wraps a closure as a reward function.
pub struct CallableRewardFn {
    name: String,
    f: Box<dyn Fn(&Step) -> f64 + Send + Sync>,
}

impl CallableRewardFn {
    pub fn new(name: impl Into<String>, f: impl Fn(&Step) -> f64 + Send + Sync + 'static) -> Self {
        Self {
            name: name.into(),
            f: Box::new(f),
        }
    }
}

impl std::fmt::Debug for CallableRewardFn {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("CallableRewardFn")
            .field("name", &self.name)
            .finish()
    }
}

impl RewardFn for CallableRewardFn {
    fn name(&self) -> &str {
        &self.name
    }

    fn score(&self, step: &Step) -> f64 {
        (self.f)(step)
    }
}
