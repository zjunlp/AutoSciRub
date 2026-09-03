from __future__ import annotations

import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/autoscirub/skills/scientific-literature-grounding/scripts/retrieve_literature.py"
MODULE = runpy.run_path(str(SCRIPT))


class RetrievalConfigTests(unittest.TestCase):
    def test_fallback_parser_reads_official_example_lists(self) -> None:
        text = (ROOT / "config/sources.example.yaml").read_text(encoding="utf-8")
        parsed = MODULE["simple_yaml"](text)

        self.assertEqual(
            parsed["retrieval"]["enabled_sources"],
            ["local_literature", "arxiv", "openalex", "semantic_scholar", "tavily", "web"],
        )
        self.assertEqual(parsed["retrieval"]["exclusions"]["excluded_paths"], [])
        MODULE["validate_config"](MODULE["deep_merge"](MODULE["DEFAULT_CONFIG"], parsed))

    def test_load_config_works_without_pyyaml(self) -> None:
        example = ROOT / "config/sources.example.yaml"
        with patch.dict(sys.modules, {"yaml": None}):
            config = MODULE["load_config"](example)

        self.assertIn("arxiv", config["retrieval"]["enabled_sources"])
        self.assertEqual(config["retrieval"]["exclusions"]["excluded_paths"], [])

    def test_invalid_list_type_is_rejected(self) -> None:
        config = MODULE["deep_merge"](
            MODULE["DEFAULT_CONFIG"],
            {"retrieval": {"enabled_sources": {}}},
        )

        with self.assertRaisesRegex(MODULE["ConfigError"], "enabled_sources must be a list"):
            MODULE["validate_config"](config)

    def test_missing_config_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.yaml"
            with self.assertRaisesRegex(MODULE["ConfigError"], "Configuration file not found"):
                MODULE["load_config"](missing)

    def test_unsupported_fallback_yaml_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE["ConfigError"], "only scalar list items"):
            MODULE["simple_yaml"]("items:\n  - name: paper\n")


if __name__ == "__main__":
    unittest.main()
