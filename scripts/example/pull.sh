#!/bin/bash

set -euo pipefail

REPO_URL="https://github.com/igeniusai/mcp-investment-demo.git"
TARGET_DIR="services/example2"

rm -rf "$TARGET_DIR"

git clone "$REPO_URL" "$TARGET_DIR"

rm -rf "$TARGET_DIR/.git"
rm -rf "$TARGET_DIR/.vscode"
