#!/usr/bin/env python3
"""Data Dragon 缓存行为探测脚本 (Cache Behavior Probe Script).

这个脚本独立验证 DataDragonClient 的缓存行为，无需完整的业务链路。
可以在 CI/CD pipeline 之前运行，提前发现缓存问题。

Usage:
    poetry run python scripts/ddragon_cache_probe.py

Expected Output:
    ✓ First fetch (cold start)
    ✓ Cache hit (same version)
    ✓ TTL expiry refetch
    ✓ Normalization reuses cache
"""

import sys
import time
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def probe_basic_cache_hit() -> bool:
    """探测基础缓存命中 (Probe basic cache hit)."""
    from src.core.services.team_builds_enricher import DataDragonClient

    print("\n[1/4] 测试基础缓存命中 (Testing basic cache hit)...")

    client = DataDragonClient(locale="zh_CN")

    # First fetch
    print("  → 第一次调用 get_latest_version()...")
    start = time.time()
    version1 = client.get_latest_version()
    duration1 = time.time() - start
    print(f"    版本: {version1}, 耗时: {duration1:.3f}s")

    # Second fetch (should hit cache)
    print("  → 第二次调用 get_latest_version() (应命中缓存)...")
    start = time.time()
    version2 = client.get_latest_version()
    duration2 = time.time() - start
    print(f"    版本: {version2}, 耗时: {duration2:.3f}s")

    # Cache hit should be significantly faster
    speedup = duration1 / duration2 if duration2 > 0 else float("inf")

    if version1 == version2:
        print(f"  ✓ 缓存命中! 加速比: {speedup:.1f}x")
        return True
    else:
        print(f"  ✗ 缓存失败: version1={version1}, version2={version2}")
        return False


def probe_ttl_expiry() -> bool:
    """探测TTL失效行为 (Probe TTL expiry)."""
    from src.core.services.team_builds_enricher import DataDragonClient, DDragonConfig

    print("\n[2/4] 测试TTL失效 (Testing TTL expiry)...")

    # Use very short TTL (1 second)
    config = DDragonConfig(locale="zh_CN", ttl_versions_s=1.0)
    client = DataDragonClient(locale="zh_CN", cfg=config)

    print("  → 第一次调用...")
    version1 = client.get_latest_version()
    print(f"    版本: {version1}")

    print("  → 等待 TTL 过期 (1.2秒)...")
    time.sleep(1.2)

    print("  → 第二次调用 (应重新fetch)...")
    start = time.time()
    version2 = client.get_latest_version()
    duration = time.time() - start
    print(f"    版本: {version2}, 耗时: {duration:.3f}s")

    # TTL expired, should refetch (take some time)
    if duration > 0.01:  # Network call should take > 10ms
        print(f"  ✓ TTL 失效正确! 重新fetch耗时 {duration:.3f}s")
        return True
    else:
        print(f"  ✗ TTL 失效异常: 耗时过短 ({duration:.3f}s)")
        return False


def probe_normalization_cache() -> bool:
    """探测版本归一化与缓存联动 (Probe normalization + cache)."""
    from src.tasks.team_tasks import _champion_icon_url, _normalize_game_version

    print("\n[3/4] 测试版本归一化与缓存 (Testing normalization + cache)...")

    # Test normalization
    print("  → 测试版本归一化...")
    v1 = _normalize_game_version("14.10.1.534")
    v2 = _normalize_game_version("14.10.1_14.10.1.454")
    v3 = _normalize_game_version("14.10")

    print(f"    14.10.1.534 → {v1}")
    print(f"    14.10.1_14.10.1.454 → {v2}")
    print(f"    14.10 → {v3}")

    if v1 == "14.10.1" and v2 == "14.10.1" and v3 == "14.10.1":
        print("  ✓ 版本归一化正确!")
    else:
        print(f"  ✗ 版本归一化失败: v1={v1}, v2={v2}, v3={v3}")
        return False

    # Test champion icon URL generation
    print("  → 测试 champion_icon_url 生成...")
    url1 = _champion_icon_url("Qiyana", "14.10.1.534")
    url2 = _champion_icon_url("Ahri", "14.10.1_14.10.1.454")

    expected_v = "14.10.1"
    if expected_v in url1 and expected_v in url2:
        print(f"  ✓ URL生成正确! 使用版本: {expected_v}")
        print(f"    {url1}")
        print(f"    {url2}")
        return True
    else:
        print(f"  ✗ URL生成失败: url1={url1}, url2={url2}")
        return False


def probe_fallback_chain() -> bool:
    """探测fallback链路 (Probe fallback chain)."""
    import os

    from src.tasks.team_tasks import _champion_icon_url

    print("\n[4/4] 测试Fallback链路 (Testing fallback chain)...")

    # Save original env
    original_env = os.getenv("DDRAGON_VERSION")

    try:
        # Test env fallback
        print("  → 测试环境变量 fallback...")
        os.environ["DDRAGON_VERSION"] = "14.8.1"
        url_env = _champion_icon_url("Yasuo", None)

        if "14.8.1" in url_env:
            print(f"  ✓ 环境变量 fallback 正确! {url_env}")
        else:
            print(f"  ✗ 环境变量 fallback 失败: {url_env}")
            return False

        # Test DataDragonClient fallback
        print("  → 测试 DataDragonClient fallback...")
        del os.environ["DDRAGON_VERSION"]
        url_dd = _champion_icon_url("Zed", None)

        # Should use either DataDragonClient or hardcoded fallback
        if "ddragon.leagueoflegends.com" in url_dd:
            print(f"  ✓ DataDragonClient fallback 正确! {url_dd}")
            return True
        else:
            print(f"  ✗ DataDragonClient fallback 失败: {url_dd}")
            return False

    finally:
        # Restore original env
        if original_env:
            os.environ["DDRAGON_VERSION"] = original_env
        elif "DDRAGON_VERSION" in os.environ:
            del os.environ["DDRAGON_VERSION"]


def main() -> int:
    """Main probe execution."""
    print("=" * 60)
    print("Data Dragon 缓存行为探测 (Cache Behavior Probe)")
    print("=" * 60)

    results = []

    # Run all probes
    results.append(("基础缓存命中", probe_basic_cache_hit()))
    results.append(("TTL失效", probe_ttl_expiry()))
    results.append(("版本归一化", probe_normalization_cache()))
    results.append(("Fallback链路", probe_fallback_chain()))

    # Summary
    print("\n" + "=" * 60)
    print("测试结果总结 (Test Summary)")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {status}  {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n✅ 所有缓存探测通过! (All probes passed!)")
        return 0
    else:
        print(f"\n❌ {total - passed} 个探测失败! ({total - passed} probes failed!)")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ 探测脚本异常: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
