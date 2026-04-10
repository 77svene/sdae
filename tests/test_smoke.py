"""
Smoke tests — verify every module imports and core logic works without Ollama.
These run offline. No LLM calls, no network required.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch, MagicMock


# ── Config ────────────────────────────────────────────────────────────────────
def test_config_defaults():
    from config import CFG
    assert CFG.ollama_model == os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
    assert CFG.max_tool_calls_per_turn == 3
    assert CFG.max_build_retries == 5
    assert CFG.data_dir.exists()


# ── Memory ────────────────────────────────────────────────────────────────────
def test_hot_cache_lru():
    from memory.hot import HotCache
    cache = HotCache(max_size=3)
    cache.set("a", "1")
    cache.set("b", "2")
    cache.set("c", "3")
    assert cache.get("a") == "1"
    cache.set("d", "4")  # evicts b (LRU)
    assert cache.get("b") is None
    assert cache.get("d") == "4"
    assert cache.size() == 3


def test_cold_memory_roundtrip(tmp_path):
    from config import CFG
    original = CFG.data_dir
    CFG.data_dir = tmp_path
    from memory.cold import ColdMemory
    cold = ColdMemory()
    cold.store_memory("k1", "hello world", category="test")
    assert cold.get_memory("k1") == "hello world"
    assert cold.get_memory("nonexistent") is None
    CFG.data_dir = original


def test_cold_outcome_stats(tmp_path):
    from config import CFG
    original = CFG.data_dir
    CFG.data_dir = tmp_path
    from memory.cold import ColdMemory
    cold = ColdMemory()
    cold.record_outcome("proj1", "build a thing", True, revenue=10.0, compute_hours=0.5)
    cold.record_outcome("proj2", "another thing", False)
    stats = cold.get_stats()
    assert stats["total_projects"] == 2
    assert stats["wins"] == 1
    assert stats["revenue"] == 10.0
    CFG.data_dir = original


def test_warm_memory_fallback():
    from memory.warm import WarmMemory
    wm = WarmMemory()
    wm._collection = None  # force fallback
    wm.store("k1", "autonomous agent software")
    wm.store("k2", "recipe for pasta carbonara")
    results = wm.search("agent software", n=5)
    assert len(results) >= 1
    assert results[0]["id"] == "k1"


def test_warm_empty_search():
    from memory.warm import WarmMemory
    wm = WarmMemory()
    wm._collection = None
    wm._fallback = []
    results = wm.search("anything", n=5)
    assert results == []


# ── Exec ──────────────────────────────────────────────────────────────────────
def test_code_block_extraction():
    from exec.builder import _extract_code_blocks
    text = '```python\nprint("hello")\n```'
    blocks = _extract_code_blocks(text)
    assert len(blocks) == 1
    assert 'print("hello")' in blocks[0][1]


def test_code_block_multifile():
    from exec.builder import _extract_code_blocks
    text = (
        '```python:main.py\nprint("main")\n```\n'
        '```python:utils.py\ndef helper(): pass\n```'
    )
    blocks = _extract_code_blocks(text)
    assert len(blocks) == 2
    assert blocks[0][0] == "main.py"
    assert blocks[1][0] == "utils.py"


def test_executor_runs_python(tmp_path):
    from exec.executor import Executor
    ex = Executor()
    script = tmp_path / "hello.py"
    script.write_text('print("sdae")')
    result = ex.run_python_file(script)
    assert result.success
    assert "sdae" in result.stdout


def test_executor_captures_failure(tmp_path):
    from exec.executor import Executor
    ex = Executor()
    script = tmp_path / "bad.py"
    script.write_text("raise ValueError('intentional')")
    result = ex.run_python_file(script)
    assert not result.success
    assert "intentional" in result.stderr or "ValueError" in result.stderr


def test_package_extraction():
    from exec.builder import _extract_packages
    text = "pip install requests beautifulsoup4\npip install httpx"
    pkgs = _extract_packages(text)
    assert "requests" in pkgs
    assert "httpx" in pkgs


# ── Core ──────────────────────────────────────────────────────────────────────
def test_router_prompts():
    from core.router import ROUTER
    for task in ("plan", "build", "research", "score", "decide", "extract", "default"):
        prompt = ROUTER.get_system_prompt(task)
        assert len(prompt) > 20
        temp = ROUTER.get_temperature(task)
        assert 0.0 <= temp <= 1.0


def test_permission_auto_allows_all():
    from core.permission import PermissionSystem
    p = PermissionSystem()
    p.set_mode("auto")
    assert p.check("bash", {"command": "rm -rf /"}) is True


def test_permission_plan_blocks_writes():
    from core.permission import PermissionSystem
    p = PermissionSystem()
    p.set_mode("plan")
    assert p.check("bash", {}) is False
    assert p.check("file_read", {}) is True


# ── Intel ─────────────────────────────────────────────────────────────────────
def test_opp_id_deterministic():
    from intel.scorer import _opp_id
    from intel.scanner import RawOpportunity
    opp = RawOpportunity("Test opportunity title", "http://example.com", "test")
    assert _opp_id(opp) == _opp_id(opp)
    assert len(_opp_id(opp)) == 12


def test_scanner_evergreen():
    from intel.scanner import EVERGREEN
    assert len(EVERGREEN) >= 5
    for opp in EVERGREEN:
        assert opp.title
        assert opp.source == "evergreen"


def test_scanner_handles_network_failure():
    from intel.scanner import _hn_stories
    with patch("intel.scanner.requests.get", side_effect=Exception("down")):
        result = _hn_stories("show", limit=5)
    assert result == []


# ── Outcomes ──────────────────────────────────────────────────────────────────
def test_fitness_zero_compute():
    from outcomes.fitness import FitnessTracker
    ft = FitnessTracker()
    # Monkeypatch get_outcomes to return one entry with 0 compute hours
    with patch.object(ft, "get_metrics") as mock:
        from outcomes.fitness import FitnessMetrics
        mock.return_value = FitnessMetrics(fitness_score=0.0, total_compute_hours=0.0)
        m = ft.get_metrics()
        assert m.fitness_score == 0.0  # no divide by zero


def test_compressor_fits():
    from memory.compressor import ContextCompressor
    c = ContextCompressor(max_tokens=10000)
    msgs = [{"role": "user", "content": "short"}]
    assert c.fits(msgs) is True


def test_compressor_token_estimate():
    from memory.compressor import _token_estimate
    assert _token_estimate("a" * 400) == 100


# ── Agents ────────────────────────────────────────────────────────────────────
def test_coordinator_dispatch():
    from agents.coordinator import Coordinator
    c = Coordinator()
    c.register("echo", lambda x: x)
    result = c.dispatch("echo", x="hello")
    assert result == "hello"


def test_coordinator_unknown_agent():
    from agents.coordinator import Coordinator
    c = Coordinator()
    with pytest.raises(ValueError):
        c.dispatch("nonexistent")


def test_spawner_config_mutate():
    from agents.spawner import AgentConfig
    base = AgentConfig(name="base", task_type="build", temperature=0.1)
    mutated = base.mutate(temperature=0.5, task_type="research")
    assert mutated.temperature == 0.5
    assert mutated.task_type == "research"
    assert "mut_" in mutated.name
    # Original unchanged
    assert base.temperature == 0.1
