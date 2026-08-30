# Local algorithm runtimes

Large, algorithm-specific Python environments live below this directory and are
ignored by Git. They are mounted into their worker container at runtime so GPU
dependencies do not inflate the CareShield service image or consume Docker's
root partition.

Create the GVHMR runtime with:

```bash
./scripts/bootstrap_gvhmr_runtime.sh
```

The resulting `runtime/gvhmr-env/` is local machine state and must not be
committed.
