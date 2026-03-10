# Python Standards

## Runtime

- Python `3.12+`
- PEP8 style
- Max line length `120`
- `snake_case` for functions, variables, and modules

## Type Safety

- Type hints on all public functions
- Pydantic validation at module boundaries
- Public service contracts must use typed models, not raw dictionaries
- Raise typed exceptions rather than mixed error payloads

## Documentation

- Docstrings are required on public and private functions and methods
- Keep docstrings short and purpose-focused

## Layering Rules

1. Provider HTTP access only in provider modules
2. SQL only in repository modules
3. Services orchestrate providers and repositories without raw HTTP or SQL
4. Services depend on interfaces and shared domain models, not concrete providers or storage rows

## Reliability

- Use `tenacity` for transient provider retries
- Enforce request timeouts on every HTTP call
- Emit structured logs with run and model metadata

## Testing

- Use `pytest`
- Mock HTTP calls in tests
- Validate retry behavior, error mapping, serialization, repository behavior, and orchestration flow
