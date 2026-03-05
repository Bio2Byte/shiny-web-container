# Contributing

Thanks for contributing to this template.

## Development Flow

1. Fork and create a feature branch.
2. Keep changes minimal and focused.
3. Verify the stack runs locally:
   - `docker compose up --build`
4. Validate both endpoints:
   - `http://localhost:8000/rlang-app`
   - `http://localhost:8000/python-app`
5. Open a pull request with:
   - problem statement
   - implementation details
   - test evidence

## Standards

- Prefer simple solutions and small blast radius.
- Preserve backward compatibility unless explicitly discussed.
- Do not commit secrets, credentials, or sensitive data.

## Commit Guidance

- Use clear, imperative commit messages.
- Include only files related to the change.

