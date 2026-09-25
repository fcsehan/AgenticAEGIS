"""Tests for the aegis dip CLI command."""

from aegis.cli import _build_parser


class TestDipArgParsing:
    def test_minimal_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["dip", "test.md", "-n", "test"])
        assert args.command == "dip"
        assert args.source == "test.md"
        assert args.name == "test"
        assert args.source_type == "auto"
        assert args.language == "auto"

    def test_all_args(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([
            "dip", "https://example.com/topics/",
            "-n", "gdpr",
            "-o", "/tmp/out",
            "--source-type", "html-index",
            "--language", "en",
            "--domain-context", "GDPR data protection",
            "--provider", "lm-studio",
            "--model", "qwen",
            "--dry-run",
            "--stats",
            "--batch-size", "10",
        ])
        assert args.source == "https://example.com/topics/"
        assert args.name == "gdpr"
        assert str(args.output) == "/tmp/out"
        assert args.source_type == "html-index"
        assert args.language == "en"
        assert args.domain_context == "GDPR data protection"
        assert args.provider == "lm-studio"
        assert args.model == "qwen"
        assert args.dry_run is True
        assert args.stats is True
        assert args.batch_size == 10

    def test_defaults(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(["dip", "policy.md", "-n", "corp"])
        assert args.output is None
        assert args.provider == "anthropic"
        assert args.model == "claude-sonnet-4-6"
        assert args.dry_run is False
        assert args.stats is False
        assert args.batch_size == 5
        assert args.domain_context == ""
