# Reviewed image build

Temporary infrastructure for one explicitly approved build of the public Cirujano optimization verification image. The integration/default branch is `develop`. The workflow runs only on manual dispatch, requires the exact reviewed commit, and rejects reruns. There is no application or production deployment.

The `context/` directory contains only pinned dependency manifests, the trusted harness and the image recipe. Dependency fetches ignore scripts and pnpm hooks. An offline container probe verifies Node/pnpm, the reporter alias, harness, recipe, lockfile and dependency store before any provider credential is supplied.

The publication step receives one temporary Cloud IAM token through a repository secret and stdin. Pinned Skopeo converts the Docker archive to registry format, uploads once and reads back the new platform manifest and tag. Compression may change the archive manifest digest; the destination config must match the probed immutable image config. The receipt records the actual new platform digest. The old Mac image digest is never substituted.

After the owned run, preserve its receipt, disable the workflow and remove the temporary secret. Retain this repository with zero secrets if deletion permission is unavailable. Nebius Sandbox import, model calls and comparison runs require their own verified image binding and authority.

Fresh fetches change pnpm index `checkedAt` timestamps. The probe checks fixed hashes for all package payload files and all other index metadata, then validates the entire unnormalized store against the fresh image manifest. Every image retains its own full store hash.
