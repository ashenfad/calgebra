# Contributing to calgebra

## Documentation

calgebra makes its documentation available programmatically via the `calgebra.docs` dictionary. This enables AI agents and code-aware tools to access the same documentation that humans read.

### Updating Documentation

When you update documentation files (`README.md`, `TUTORIAL.md`, or `API.md`), you must sync them to the package directory:

```bash
./sync_docs.sh
```

This ensures the documentation is included in PyPI distributions and accessible at runtime.

### Documentation Structure

- **Root directory**: Primary documentation files edited by humans
  - `README.md` - Package overview and quick start (for discovery)
  - `TUTORIAL.md` - Comprehensive guide with examples (for learning)
  - `API.md` - API reference (for reference)

- **`calgebra/docs/`**: Copies included in the package distribution
  - Synced from root via `sync_docs.sh`
  - Loaded at import time as `calgebra.docs["readme"]`, `calgebra.docs["tutorial"]`, and `calgebra.docs["api"]`
  - Enables agents to discover (readme), learn (tutorial), and reference (api) the library programmatically

### Testing

Run tests to ensure documentation is accessible:

```bash
pytest tests/test_docs.py
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/ashenfad/calgebra.git
cd calgebra

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode
pip install -e .

# Install development dependencies
pip install -e .[dev]
```

### Running Tests

```bash
# All tests
pytest tests/

# Specific test file
pytest tests/test_timeline.py -v

# With coverage
pytest --cov=calgebra tests/
```

### Code Style

We use `ruff` for linting and `black` for formatting:

```bash
ruff check calgebra/
black calgebra/
```

