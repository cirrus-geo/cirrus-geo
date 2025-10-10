import pytest

from cirrus.management.utils.templating import (
    DefaultableTemplate,
    template_payload,
)


def test_basic_substitution():
    """Test basic $var syntax with provided value."""
    template = "Hello $name"
    mapping = {"name": "World"}
    result = template_payload(template, mapping)
    assert result == "Hello World"


def test_braced_substitution():
    """Test basic ${var} syntax with provided value."""
    template = "Hello ${name}"
    mapping = {"name": "World"}
    result = template_payload(template, mapping)
    assert result == "Hello World"


def test_mixed_syntax():
    """Test mix of $var and ${var} in same template."""
    template = "Hello $name, welcome to ${place}"
    mapping = {"name": "Alice", "place": "Wonderland"}
    result = template_payload(template, mapping)
    assert result == "Hello Alice, welcome to Wonderland"


def test_escaped_dollar():
    """Test that $$ produces literal $."""
    template = "Price: $$50"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "Price: $50"


def test_default_value_used():
    """Test ${var?default} when var not provided."""
    template = "Hello ${name?Guest}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "Hello Guest"


def test_default_value_ignored():
    """Test ${var?default} when var IS provided - should use provided value."""
    template = "Hello ${name?Guest}"
    mapping = {"name": "Alice"}
    result = template_payload(template, mapping)
    assert result == "Hello Alice"


def test_empty_string_default():
    """Test ${var?} (empty default)."""
    template = "Value: ${missing?}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "Value: "


def test_default_with_spaces():
    """Test ${var?default with spaces}."""
    template = "Message: ${msg?default with spaces}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "Message: default with spaces"


def test_default_with_special_chars():
    """Test ${var?default-with_special!chars@123}."""
    template = "Value: ${val?default-with_special!chars@123}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "Value: default-with_special!chars@123"


def test_multiple_defaults():
    """Test multiple variables with defaults in one template."""
    template = "Hello ${name?Guest}, welcome to ${place?Earth} at ${time?midnight}"
    mapping = {"place": "Mars"}
    result = template_payload(template, mapping)
    assert result == "Hello Guest, welcome to Mars at midnight"


def test_default_with_question_marks():
    template = "URL: ${url?http://example.com:8080/path?param=1234}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "URL: http://example.com:8080/path?param=1234"


def test_missing_variable_substitute():
    """Test missing var with substitute() should raise KeyError."""
    template = "Hello ${name}"
    mapping = {}
    with pytest.raises(KeyError):
        template_payload(template, mapping, silence_templating_errors=False)


def test_missing_variable_safe_substitute():
    """Test missing var with safe_substitute() should leave placeholder."""
    template = "Hello ${name}"
    mapping = {}
    result = template_payload(template, mapping, silence_templating_errors=True)
    assert result == "Hello ${name}"


def test_silence_templating_errors_false():
    """Test silence_templating_errors=False uses substitute()."""
    template = "Hello ${name}"
    mapping = {"name": "World"}
    result = template_payload(template, mapping, silence_templating_errors=False)
    assert result == "Hello World"


def test_silence_templating_errors_true():
    """Test silence_templating_errors=True uses safe_substitute()."""
    template = "Hello ${name}"
    mapping = {"name": "World"}
    result = template_payload(template, mapping, silence_templating_errors=True)
    assert result == "Hello World"


def test_empty_template():
    """Test empty string template."""
    template = ""
    mapping = {"name": "World"}
    result = template_payload(template, mapping)
    assert result == ""


def test_empty_mapping():
    """Test empty mapping dict with template containing defaults."""
    template = "Hello ${name?World}, today is ${day?Monday}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "Hello World, today is Monday"


def test_no_variables():
    """Test template with no variables at all."""
    template = "This is a plain string with no variables"
    mapping = {"unused": "value"}
    result = template_payload(template, mapping)
    assert result == "This is a plain string with no variables"


def test_standard_template_behavior():
    """Verify standard Template behavior still works."""
    template = "Hello $name, you are $age years old"
    mapping = {"name": "Bob", "age": "30"}
    result = template_payload(template, mapping)
    assert result == "Hello Bob, you are 30 years old"


def test_unbraced_with_question_mark_not_matched():
    """Test $var?default (no braces) should not be treated as variable with default."""
    template = "Value: $var?default"
    mapping = {"var": "test"}
    result = template_payload(template, mapping)
    # Should substitute $var and leave ?default as literal text
    assert result == "Value: test?default"


def test_real_world_example():
    """Test complex template mimicking actual use case."""
    template = """
{
    "workflow": "${workflow}",
    "collection": "${collection?default-collection}",
    "bucket": "${bucket?s3://default-bucket}",
    "prefix": "${prefix?data/}",
    "item_id": "$item_id"
}
""".strip()
    mapping = {
        "workflow": "test-workflow",
        "item_id": "test-item-001",
        "bucket": "s3://my-bucket",
    }
    result = template_payload(template, mapping)
    expected = """
{
    "workflow": "test-workflow",
    "collection": "default-collection",
    "bucket": "s3://my-bucket",
    "prefix": "data/",
    "item_id": "test-item-001"
}
""".strip()
    assert result == expected


def test_defaultable_template_handle_defaults():
    """Test handle_defaults method directly."""
    tmpl = DefaultableTemplate("${name?Guest} ${place?Home}")
    kwargs = tmpl.handle_defaults(name="Alice")
    assert kwargs["name"] == "Alice"
    assert kwargs["name?Guest"] == "Alice"
    assert kwargs["place?Home"] == "Home"


def test_defaultable_template_substitute():
    """Test DefaultableTemplate substitute method."""
    tmpl = DefaultableTemplate("Hello ${name?World}")
    result = tmpl.substitute()
    assert result == "Hello World"


def test_defaultable_template_safe_substitute():
    """Test DefaultableTemplate safe_substitute method."""
    tmpl = DefaultableTemplate("Hello ${name?World} ${missing}")
    result = tmpl.safe_substitute()
    # safe_substitute should leave missing variables as placeholders
    assert result == "Hello World ${missing}"


def test_default_overrides_provided_value():
    """Test that when a default variable is not provided, default is used."""
    template = "${api_url?https://api.example.com/v1}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "https://api.example.com/v1"


def test_default_with_environment_like_values():
    """Test defaults that look like environment variable values."""
    template = "Database: ${db_host?localhost:5432}, User: ${db_user?admin}"
    mapping = {"db_host": "prod-db.example.com:5432"}
    result = template_payload(template, mapping)
    assert result == "Database: prod-db.example.com:5432, User: admin"


def test_adjacent_variables():
    """Test adjacent variables without separators."""
    template = "${prefix?pre}${suffix?suf}"
    mapping = {"prefix": "start"}
    result = template_payload(template, mapping)
    assert result == "startsuf"


def test_variable_at_start():
    """Test variable at the very start of template."""
    template = "${var?default} followed by text"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "default followed by text"


def test_variable_at_end():
    """Test variable at the very end of template."""
    template = "text followed by ${var?default}"
    mapping = {}
    result = template_payload(template, mapping)
    assert result == "text followed by default"
