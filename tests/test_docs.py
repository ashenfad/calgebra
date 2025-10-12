"""Test that documentation is accessible programmatically."""

import calgebra


def test_docs_dict_exists() -> None:
    """Verify the docs dictionary is available."""
    assert hasattr(calgebra, "docs")
    assert isinstance(calgebra.docs, dict)


def test_docs_keys() -> None:
    """Verify expected documentation keys exist."""
    expected_keys = {"readme", "tutorial", "api"}
    assert set(calgebra.docs.keys()) == expected_keys


def test_docs_content() -> None:
    """Verify documentation content is non-empty strings."""
    for key, content in calgebra.docs.items():
        assert isinstance(content, str), f"{key} should be a string"
        assert len(content) > 0, f"{key} should not be empty"
        assert "calgebra" in content.lower(), f"{key} should mention calgebra"


def test_tutorial_has_examples() -> None:
    """Verify tutorial contains code examples."""
    tutorial = calgebra.docs["tutorial"]
    assert "```python" in tutorial
    assert "Timeline" in tutorial
    assert "Interval" in tutorial


def test_api_has_signatures() -> None:
    """Verify API doc contains function signatures."""
    api = calgebra.docs["api"]
    assert "Timeline" in api
    assert "Filter" in api
    assert "flatten" in api
