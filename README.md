# pdt-examples
pdt-examples represents real customer projects.

## purpose
These exercise real scenarios against real systems.

The purpose is to ensure that pdt works with real scenarios. It is not to verify that pdt itself works in all environments. See pdt/verify for comprehensive pdt tests.

## principles
pdt-examples:
- Must always work against pdt:master
- pdt ci fails if pdt-examples break
- pdt-examples ci fails if it doesn't work against pdt:master

## CI variables
Each app's env vars are CI/CD variables of this project. To copy them from an app's `.env` without showing a value, run `uv run scripts/push_env.py <app>`.

## todo - these go somewhere

verify docs:
- test all docs both repos: document & run tests directly from documentation
