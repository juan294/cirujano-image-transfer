# Frozen image transfer

Temporary infrastructure for one owner-approved transfer of an immutable OCI archive to Nebius Container Registry. The integration/default branch is `develop`. The only workflow is manual; it cannot run on push, release, pull request, or schedule. The archive stays in an unpublished draft release. There is no hosted application or production deployment. The bounded job preserves image digests and removes local credential files.

After safe receipts are retained, remove the temporary secret and owned repository under the approved cleanup scope. This repository is separate from the optimization proof cohort.
