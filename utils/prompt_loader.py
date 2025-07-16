"""Utility for loading and managing prompt templates from YAML files."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from jinja2 import Template
import logging

logger = logging.getLogger(__name__)


class PromptLoader:
    """Load and manage prompt templates for LLM extraction."""

    def __init__(self, prompts_dir: Optional[Path] = None):
        """Initialize the prompt loader.

        Args:
            prompts_dir: Directory containing prompt YAML files.
                        Defaults to prompts/ in project root.
        """
        if prompts_dir is None:
            # Assume we're in a subdirectory and go up to find prompts/
            current_file = Path(__file__)
            project_root = current_file.parent.parent
            prompts_dir = project_root / "prompts"

        self.prompts_dir = Path(prompts_dir)
        if not self.prompts_dir.exists():
            raise ValueError(f"Prompts directory not found: {self.prompts_dir}")

        self._cache: Dict[str, Dict[str, Any]] = {}
        self._load_all_prompts()

    def _load_all_prompts(self):
        """Load all YAML prompt files into cache."""
        for yaml_file in self.prompts_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r") as f:
                    prompt_data = yaml.safe_load(f)

                # Use filename without extension as key
                prompt_key = yaml_file.stem
                self._cache[prompt_key] = prompt_data
                logger.info(f"Loaded prompt template: {prompt_key}")

            except Exception as e:
                logger.error(f"Failed to load prompt {yaml_file}: {e}")

    def get_prompt(self, prompt_name: str) -> Dict[str, Any]:
        """Get a prompt template by name.

        Args:
            prompt_name: Name of the prompt (filename without .yaml)

        Returns:
            Dict containing the prompt template data
        """
        if prompt_name not in self._cache:
            raise ValueError(f"Prompt template not found: {prompt_name}")

        return self._cache[prompt_name]

    def render_system_prompt(self, prompt_name: str, **kwargs) -> str:
        """Render the system prompt with variables.

        Args:
            prompt_name: Name of the prompt template
            **kwargs: Variables to inject into the template

        Returns:
            Rendered system prompt string
        """
        prompt_data = self.get_prompt(prompt_name)
        template = Template(prompt_data["system_prompt"])
        return template.render(**kwargs)

    def render_user_prompt(self, prompt_name: str, **kwargs) -> str:
        """Render the user prompt with variables.

        Args:
            prompt_name: Name of the prompt template
            **kwargs: Variables to inject into the template

        Returns:
            Rendered user prompt string
        """
        prompt_data = self.get_prompt(prompt_name)
        template = Template(prompt_data["user_prompt"])
        return template.render(**kwargs)

    def get_few_shot_examples(self, prompt_name: str) -> list:
        """Get few-shot examples for a prompt.

        Args:
            prompt_name: Name of the prompt template

        Returns:
            List of few-shot examples
        """
        prompt_data = self.get_prompt(prompt_name)
        return prompt_data.get("few_shot_examples", [])

    def get_validation_rules(self, prompt_name: str) -> list:
        """Get validation rules for a prompt.

        Args:
            prompt_name: Name of the prompt template

        Returns:
            List of validation rules
        """
        prompt_data = self.get_prompt(prompt_name)
        return prompt_data.get("validation_rules", [])

    def get_prompt_for_item(self, item_no: int) -> Optional[str]:
        """Get the prompt name for a specific FDD item number.

        Args:
            item_no: FDD item number (5, 6, 7, 19, 20, 21)

        Returns:
            Prompt name if available, None otherwise
        """
        item_to_prompt = {
            5: "item5_fees",
            6: "item6_other_fees",
            7: "item7_investment",
            19: "item19_fpr",
            20: "item20_outlets",
            21: "item21_financials",
        }

        return item_to_prompt.get(item_no)

    def format_with_examples(
        self, prompt_name: str, include_examples: bool = True, max_examples: int = 2
    ) -> str:
        """Format a complete prompt including few-shot examples.

        Args:
            prompt_name: Name of the prompt template
            include_examples: Whether to include few-shot examples
            max_examples: Maximum number of examples to include

        Returns:
            Formatted prompt string with examples
        """
        prompt_data = self.get_prompt(prompt_name)

        # Start with system prompt
        full_prompt = prompt_data["system_prompt"]

        # Add few-shot examples if requested
        if include_examples:
            examples = self.get_few_shot_examples(prompt_name)[:max_examples]
            if examples:
                full_prompt += "\n\nHere are some examples:\n\n"
                for i, example in enumerate(examples, 1):
                    full_prompt += f"Example {i}:\n"
                    full_prompt += f"Input: {example['input']}\n"
                    full_prompt += f"Output: {example['output']}\n\n"

        return full_prompt


# Singleton instance
_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader() -> PromptLoader:
    """Get the singleton prompt loader instance."""
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader
