import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[2]))

from src.fetchers.builder import load_sources_config


def test_load_sources_config_adds_chain_aware_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - name: ethereum_foundation_esp\n"
        "    fetch_method: rss\n"
        "    category: grant\n"
        "    ecosystem: ethereum\n"
        "    enabled: true\n"
        "  - name: tavily_grants_discovery\n"
        "    fetch_method: tavily_search\n"
        "    category: grant\n"
        "    ecosystem: multi\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    config = load_sources_config(str(path))

    official = config["sources"][0]
    discovery = config["sources"][1]

    assert official["chain"] == "ethereum"
    assert official["source_tier"] == "official"
    assert official["official"] is True
    assert official["signal_type"] == "grant"

    assert discovery["chain"] == "multi"
    assert discovery["source_tier"] == "discovery"
    assert discovery["official"] is False
    assert discovery["signal_type"] == "discovery"


def test_load_sources_config_preserves_explicit_chain_aware_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - name: ethglobal\n"
        "    fetch_method: rss\n"
        "    category: hackathon\n"
        "    ecosystem: ethereum\n"
        "    chain: multi\n"
        "    source_tier: discovery\n"
        "    signal_type: hackathon\n"
        "    official: false\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    config = load_sources_config(str(path))
    source = config["sources"][0]

    assert source["chain"] == "multi"
    assert source["source_tier"] == "discovery"
    assert source["signal_type"] == "hackathon"
    assert source["official"] is False


def test_load_sources_config_backfills_social_metadata_for_twitter_sources(tmp_path: Path) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - name: twitter_base\n"
        "    fetch_method: twitter\n"
        "    category: social\n"
        "    ecosystem: base\n"
        "    schedule: social_watch\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    config = load_sources_config(str(path))
    source = config["sources"][0]

    assert source["signal_type"] == "social"
    assert source["trust_tier"] == "official"
    assert source["ingestion_mode"] == "direct"
    assert source["source_kind"] == "account"
    assert source["watch_priority"] == "normal"


def test_load_sources_config_applies_default_tavily_success_cooldown(tmp_path: Path, isolated_defaults) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - name: tavily_grants_discovery\n"
        "    fetch_method: tavily_search\n"
        "    category: grant\n"
        "    ecosystem: multi\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    config = load_sources_config(str(path))
    source = config["sources"][0]

    assert source["success_cooldown_minutes"] == 5760


def test_load_sources_config_applies_default_tavily_budget(tmp_path: Path, isolated_defaults) -> None:
    path = tmp_path / "sources.yaml"
    path.write_text(
        "sources:\n"
        "  - name: tavily_hackathons_discovery\n"
        "    fetch_method: tavily_search\n"
        "    category: hackathon\n"
        "    ecosystem: multi\n"
        "    enabled: true\n",
        encoding="utf-8",
    )

    config = load_sources_config(str(path))
    source = config["sources"][0]

    assert source["max_sources_per_run"] == 1
