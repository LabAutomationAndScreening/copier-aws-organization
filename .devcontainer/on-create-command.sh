#!/bin/bash
set -ex

# For some reason the directory is not setup correctly and causes build of devcontainer to fail since
# it doesn't have access to the workspace directory. This can normally be done in post-start-command
git config --global --add safe.directory /workspaces/copier-aws-organization

sh .devcontainer/on-create-command-boilerplate.sh

pre-commit install --install-hooks

python .devcontainer/manual-setup-deps.py --optionally-check-lock
