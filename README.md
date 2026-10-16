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

## demo

`monday-orphaned-account-report/demo/` runs the orphan report without a real Entra tenant. See that folder's README for the all-mock command and the real-Monday plus fake-Entra command.

## todo - these go somewhere

verify docs:
- test all docs both repos: document & run tests directly from documentation
