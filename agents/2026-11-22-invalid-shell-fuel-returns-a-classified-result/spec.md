# Invalid shell fuel returns a classified result

Draft, 2026-11-22. Detailed finding from the shell review of `cbda2721`.

## The outcome wanted

run_line validates fuel before constructing the native machine.

## The problem

Named limits receive Python range and type checks. Fuel is passed directly to an unsigned native parameter, so invalid values can raise conversion exceptions.

## Proposed changes

Validate fuel against its native unsigned range and reject booleans consistently with named budgets. Preserve the default when omitted.

## Acceptance tests

Test a valid boundary, zero, a negative value, a boolean and an out-of-range integer. Assert invalid inputs return classified errors before native construction.

## Builds on

[src/vfs/shell/host.py L237](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L237) · [src/vfs/shell/host.py L255](https://github.com/ClayGendron/vfs/blob/cbda27211fe165099c4843dad1464df6c8da0fe1/src/vfs/shell/host.py#L255)
