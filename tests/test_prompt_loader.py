"""Tests for prompt loader utility."""

import pytest
import yaml
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open

from utils.prompt_loader import PromptLoader, get_prompt_loader


class TestPromptLoader:
    """Test suite for PromptLoader class."""

    @pytest.fixture
    def temp_prompts_dir(self):
        """Create temporary prompts directory with test files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            prompts_dir = Path(temp_dir) / "prompts"
            prompts_dir.mkdir()

            # Create test prompt files
            test_prompts = {
                "item5_fees.yaml": {
                    "name": "Item 5 - Initial Fees",
                    "system_prompt": "Extract franchise fees from Item 5",
                    "user_prompt": "Extract from: {{ section_content }}",
                    "few_shot_examples": [
                        {"input": "Fee is $45,000", "output": {"base_fee": 45000}}
                    ],
                    "validation_rules": [
                        {"field": "base_fee", "type": "number", "required": True}
                    ],
                },
                "item7_investment.yaml": {
                    "name": "Item 7 - Investment",
                    "system_prompt": "Extract investment table",
                    "user_prompt": "Document: {{ franchise_name }}\nContent: {{ section_content }}",
                    "few_shot_examples": [],
                    "validation_rules": [],
                },
            }

            for filename, content in test_prompts.items():
                with open(prompts_dir / filename, "w") as f:
                    yaml.dump(content, f)

            yield prompts_dir

    def test_prompt_loader_initialization(self, temp_prompts_dir):
        """Test PromptLoader initialization and loading."""
        loader = PromptLoader(temp_prompts_dir)

        # Check that prompts were loaded
        assert "item5_fees" in loader._cache
        assert "item7_investment" in loader._cache
        assert len(loader._cache) == 2

    def test_prompt_loader_missing_directory(self):
        """Test PromptLoader with missing directory."""
        with pytest.raises(ValueError, match="Prompts directory not found"):
            PromptLoader(Path("/non/existent/directory"))

    def test_get_prompt(self, temp_prompts_dir):
        """Test getting a prompt by name."""
        loader = PromptLoader(temp_prompts_dir)

        prompt = loader.get_prompt("item5_fees")
        assert prompt["name"] == "Item 5 - Initial Fees"
        assert prompt["system_prompt"] == "Extract franchise fees from Item 5"
        assert len(prompt["few_shot_examples"]) == 1

    def test_get_prompt_not_found(self, temp_prompts_dir):
        """Test getting non-existent prompt."""
        loader = PromptLoader(temp_prompts_dir)

        with pytest.raises(ValueError, match="Prompt template not found"):
            loader.get_prompt("non_existent")

    def test_render_system_prompt(self, temp_prompts_dir):
        """Test rendering system prompt with variables."""
        loader = PromptLoader(temp_prompts_dir)

        rendered = loader.render_system_prompt("item5_fees")
        assert rendered == "Extract franchise fees from Item 5"

        # System prompt doesn't have variables in this test
        rendered_with_vars = loader.render_system_prompt(
            "item5_fees", franchise_name="Test Franchise"
        )
        assert rendered_with_vars == "Extract franchise fees from Item 5"

    def test_render_user_prompt(self, temp_prompts_dir):
        """Test rendering user prompt with variables."""
        loader = PromptLoader(temp_prompts_dir)

        rendered = loader.render_user_prompt(
            "item5_fees", section_content="The fee is $50,000"
        )
        assert rendered == "Extract from: The fee is $50,000"

        # Test with multiple variables
        rendered = loader.render_user_prompt(
            "item7_investment",
            franchise_name="Test Franchise",
            section_content="Investment table here",
        )
        assert "Document: Test Franchise" in rendered
        assert "Content: Investment table here" in rendered

    def test_get_few_shot_examples(self, temp_prompts_dir):
        """Test getting few-shot examples."""
        loader = PromptLoader(temp_prompts_dir)

        examples = loader.get_few_shot_examples("item5_fees")
        assert len(examples) == 1
        assert examples[0]["input"] == "Fee is $45,000"
        assert examples[0]["output"]["base_fee"] == 45000

        # Test prompt without examples
        examples = loader.get_few_shot_examples("item7_investment")
        assert examples == []

    def test_get_validation_rules(self, temp_prompts_dir):
        """Test getting validation rules."""
        loader = PromptLoader(temp_prompts_dir)

        rules = loader.get_validation_rules("item5_fees")
        assert len(rules) == 1
        assert rules[0]["field"] == "base_fee"
        assert rules[0]["type"] == "number"
        assert rules[0]["required"] is True

    def test_get_prompt_for_item(self, temp_prompts_dir):
        """Test mapping item numbers to prompt names."""
        loader = PromptLoader(temp_prompts_dir)

        assert loader.get_prompt_for_item(5) == "item5_fees"
        assert loader.get_prompt_for_item(6) == "item6_other_fees"
        assert loader.get_prompt_for_item(7) == "item7_investment"
        assert loader.get_prompt_for_item(19) == "item19_fpr"
        assert loader.get_prompt_for_item(20) == "item20_outlets"
        assert loader.get_prompt_for_item(21) == "item21_financials"
        assert loader.get_prompt_for_item(2) is None  # No mapping

    def test_format_with_examples(self, temp_prompts_dir):
        """Test formatting prompt with examples."""
        loader = PromptLoader(temp_prompts_dir)

        # Test with examples
        formatted = loader.format_with_examples("item5_fees", include_examples=True)
        assert "Extract franchise fees from Item 5" in formatted
        assert "Here are some examples:" in formatted
        assert "Example 1:" in formatted
        assert "Input: Fee is $45,000" in formatted
        assert "Output: {'base_fee': 45000}" in formatted

        # Test without examples
        formatted = loader.format_with_examples("item5_fees", include_examples=False)
        assert "Extract franchise fees from Item 5" in formatted
        assert "Here are some examples:" not in formatted

    def test_format_with_examples_max_limit(self, temp_prompts_dir):
        """Test formatting with example limit."""
        loader = PromptLoader(temp_prompts_dir)

        # Even with max_examples=0, no examples should be included
        formatted = loader.format_with_examples(
            "item5_fees", include_examples=True, max_examples=0
        )
        assert "Here are some examples:" not in formatted

    def test_singleton_prompt_loader(self, temp_prompts_dir):
        """Test singleton pattern for get_prompt_loader."""
        with patch("utils.prompt_loader.PromptLoader") as mock_loader_class:
            mock_loader_class.return_value = "mock_instance"

            # First call creates instance
            loader1 = get_prompt_loader()
            assert loader1 == "mock_instance"
            mock_loader_class.assert_called_once()

            # Second call returns same instance
            loader2 = get_prompt_loader()
            assert loader2 == "mock_instance"
            # Still only called once
            mock_loader_class.assert_called_once()

    def test_load_corrupted_yaml(self, temp_prompts_dir):
        """Test handling of corrupted YAML files."""
        # Create a corrupted YAML file
        corrupted_file = temp_prompts_dir / "corrupted.yaml"
        with open(corrupted_file, "w") as f:
            f.write("invalid: yaml: content: [missing bracket")

        # Loader should skip corrupted files
        loader = PromptLoader(temp_prompts_dir)
        assert "corrupted" not in loader._cache
        # Other files should still load
        assert "item5_fees" in loader._cache
        assert "item7_investment" in loader._cache


class TestPromptLoaderIntegration:
    """Integration tests for PromptLoader with actual prompt files."""

    def test_load_actual_prompts(self):
        """Test loading actual prompt files from the project."""
        # This test would run against the actual prompts directory
        # Skip if running in isolation
        try:
            loader = get_prompt_loader()

            # Check that expected prompts are loaded
            expected_prompts = [
                "item5_fees",
                "item6_other_fees",
                "item7_investment",
                "item19_fpr",
                "item20_outlets",
                "item21_financials",
            ]

            for prompt_name in expected_prompts:
                prompt = loader.get_prompt(prompt_name)
                assert "system_prompt" in prompt
                assert "user_prompt" in prompt

        except ValueError:
            # Skip if prompts directory doesn't exist
            pytest.skip("Prompts directory not found")
