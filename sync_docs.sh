#!/bin/bash
# Sync documentation from root to package directory
# Run this after updating README.md, TUTORIAL.md, or API.md

cp README.md TUTORIAL.md API.md calgebra/docs/
echo "Documentation synced to calgebra/docs/"

