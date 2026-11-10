# Integration verification — 2026-11-10

This integration completes the pending worker launcher, explicit cloning-backend
failure handling, wheel package discovery, Dependabot configuration, documentation,
and ElevenLabs requirement changes from PRs #75, #70 and #76.

Validation on this integration: 114 Python tests and 23 Node upload tests passed;
Python compilation, shell syntax, whitespace checks, CLI help and wheel build passed.
The wheel contains the voice_cloning subpackage. GitHub CI and production deployment
must also pass on the final commit before claiming publication is verified.

Dependency decisions:

- Retain Torch and Torchaudio below 2.6 in the RVC sidecar. PRs #73 and #74
  independently raise incompatible bounds without sidecar inference evidence.
- Keep PyWorld's minimum at 0.3.5. PR #71's 0.3.6 release supplies only legacy
  Windows wheels and no source archive in the inspected PyPI release metadata;
  Linux Python 3.12 cannot install it. Both configured-index and direct-PyPI
  installation attempts reproduced this. Raising the minimum breaks Linux setup.

Public runtime checks: the frontdoor, capabilities and storage-health endpoints
returned HTTP 200. The returned queue sample still has five queued and two failed
jobs. Configured engines in that response are not proof of a running worker.
VPS health responds over its existing self-signed TLS, but SSH has no loaded
identity and no worker service credentials/configuration are present locally.
A complete public upload-to-neural-render round trip remains unverified.

Recovery: patches, initial status, an all-refs Git bundle and verification logs
are saved under the original checkout's .git/recovery directory. Integration
commits are also pushed remotely; private audio and models remain outside Git.
