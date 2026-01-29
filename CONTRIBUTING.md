# Contributing to Jeeves Infra

Thank you for your interest in contributing to Jeeves Infra!

## Before You Start

Please read our [CONSTITUTION.md](CONSTITUTION.md) to understand the architectural principles. The infrastructure layer provides reusable services without domain-specific logic.

## Contribution Guidelines

### What We're Looking For

Jeeves Infra is the **infrastructure layer**. Contributions should:

1. **Be reusable** - Can multiple capabilities use this?
2. **Avoid domain logic** - No business rules or domain-specific features
3. **Support streaming** - LLM operations should be stream-first
4. **Maintain backward compatibility** - Breaking changes require major version bumps

### Layer Boundaries

Before contributing, verify your change belongs in this layer:

| Change Type | Belongs In |
|-------------|------------|
| LLM provider adapters | jeeves-infra (here) |
| Database clients | jeeves-infra (here) |
| Runtime/pipeline execution | jeeves-infra (here) |
| Gateway/API endpoints | jeeves-infra (here) |
| Kernel state management | jeeves-core |
| Domain-specific tools | capability layer |
| Prompt templates | capability layer |

## How to Contribute

### Reporting Issues

Please use the following format for issues:

```markdown
## Summary
Brief description of the issue or feature request.

## Layer Verification
- [ ] This is infrastructure, not domain logic
- [ ] I've read CONSTITUTION.md

## Current Behavior
What happens now?

## Expected Behavior
What should happen?

## Steps to Reproduce (for bugs)
1. Step one
2. Step two
3. ...

## Environment
- Python version:
- OS:
- Package version:

## Additional Context
Any other relevant information.
```

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with tests
4. Ensure all tests pass: `pytest`
5. Submit a PR with the following template:

```markdown
## Summary
What does this PR do?

## Reusability
How can multiple capabilities use this?

## Changes
- List of changes

## Testing
- How was this tested?
- [ ] Unit tests added/updated
- [ ] Integration tests added/updated
- [ ] Mock tests (no live backend required)

## Checklist
- [ ] I've read CONSTITUTION.md
- [ ] Tests pass locally
- [ ] No domain-specific logic
- [ ] Streaming supported (for LLM changes)
- [ ] Documentation updated if needed
```

## Development Setup

```bash
# Clone the repository
git clone https://github.com/Jeeves-Cluster-Organization/jeeves-infra.git
cd jeeves-infra

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=jeeves_infra
```

## Code Style

- Follow PEP 8
- Use type hints for all public functions
- Run `black` and `ruff` before committing
- Add docstrings for exported functions

## Questions?

Open an issue with the `question` label or start a discussion.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
