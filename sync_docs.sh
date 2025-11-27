#!/bin/bash
# Sync documentation from root to package directory
# Run this after updating README.md, TUTORIAL.md, or API.md

cp README.md calgebra/docs/
cp docs/*.md calgebra/docs/
echo "Documentation synced to calgebra/docs/"

