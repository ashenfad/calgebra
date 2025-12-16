"""Test that documentation is accessible programmatically."""

import dataclasses

import calgebra


def test_docs_object_exists() -> None:
    """Verify the docs object is available."""
    assert hasattr(calgebra, "docs")
    assert isinstance(calgebra.docs, calgebra.Docs)


def test_docs_fields() -> None:
    """Verify expected documentation fields exist."""
    expected_fields = {"readme", "tutorial", "api", "gcsa", "quick_start"}
    actual_fields = {f.name for f in dataclasses.fields(calgebra.docs)}
    assert actual_fields == expected_fields


def test_docs_content() -> None:
    """Verify documentation content is non-empty strings."""
    for field in dataclasses.fields(calgebra.docs):
        content = getattr(calgebra.docs, field.name)
        assert isinstance(content, str), f"{field.name} should be a string"
        assert len(content) > 0, f"{field.name} should not be empty"
        assert "calgebra" in content.lower(), f"{field.name} should mention calgebra"


def test_tutorial_has_examples() -> None:
    """Verify tutorial contains code examples."""
    tutorial = calgebra.docs.tutorial
    assert "```python" in tutorial
    assert "Timeline" in tutorial
    assert "Interval" in tutorial


def test_api_has_signatures() -> None:
    """Verify API doc contains function signatures."""
    api = calgebra.docs.api
    assert "Timeline" in api
    assert "Filter" in api
    assert "flatten" in api
