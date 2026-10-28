"""EpisodeMapper 季集映射 — 合并季（动漫按季度连贯编号）回退测试.

回归场景：药屋少女的呢喃（TMDB 220542）在 TMDB 上是合并季 S01 共 60 集，
发布组按季度编号 S03E01 = 绝对第 49 集。此前 map_auto 对 season>1 且 episode≤26
只做"TMDB 是否已有该季"的快速检查，永远等不到 S03，直接放弃映射 → 订阅不到资源。
"""

from unittest.mock import MagicMock, patch

from app.media.parser.episode_mapper import EpisodeMapper

# TMDB 合并季：只有 S01，共 60 集（24 + 24 + 12）
MERGED_TMDB = {"id": 220542, "seasons": [{"season_number": 1, "episode_count": 60}]}
# 由 air_date 推断出的季块：S01E1-24 / S01E25-48 / S01E49-60
MERGED_BLOCKS = [(1, 1, 24), (2, 25, 48), (3, 49, 60)]
# TMDB 合并季：只有 S01，共 104 集（52 + 52）
LONG_MERGED_TMDB = {"id": 226045, "seasons": [{"season_number": 1, "episode_count": 104}]}
LONG_MERGED_BLOCKS = [(1, 1, 52), (2, 53, 104)]
# TMDB 已有独立两季，但开启映射后仍统一累计到 S01
MULTI_SEASON_TMDB = {
    "id": 1001,
    "seasons": [
        {"season_number": 1, "episode_count": 52},
        {"season_number": 2, "episode_count": 52},
    ],
}


def _mapper(tv_info, blocks):
    tmdb = MagicMock()
    tmdb.get_tmdb_info.return_value = tv_info
    mapper = EpisodeMapper(tmdb_lookup=tmdb)
    patcher = patch.object(EpisodeMapper, "_fetch_blocks", return_value=blocks)
    patcher.start()
    return mapper, patcher


class TestMergedSeasonFallback:
    """TMDB 只有合并 S01 时，发布组的季度编号应映射到绝对集号."""

    def test_season_beyond_tmdb_falls_back_to_blocks(self):
        mapper, patcher = _mapper(MERGED_TMDB, MERGED_BLOCKS)
        try:
            assert mapper.map_auto(220542, 3, 1) == (1, 49)
            assert mapper.map_auto(220542, 3, 2) == (1, 50)
            assert mapper.map_auto(220542, 2, 1) == (1, 25)
        finally:
            patcher.stop()

    def test_range_maps_both_ends(self):
        mapper, patcher = _mapper(MERGED_TMDB, MERGED_BLOCKS)
        try:
            assert mapper.map_auto(220542, 3, 1, 3) == (1, 49, 1, 51)
        finally:
            patcher.stop()

    def test_canonical_coordinates_untouched(self):
        """TMDB 已有该季且集号在范围内 → 无需映射."""
        mapper, patcher = _mapper(MERGED_TMDB, MERGED_BLOCKS)
        try:
            assert mapper.map_auto(220542, 1, 49) is None
            assert mapper.map_auto(220542, 1, 25) is None
        finally:
            patcher.stop()

    def test_normal_multi_season_show_not_remapped(self):
        """无法推断季块（正常多季剧）→ 不猜测、不映射."""
        normal = {
            "id": 1396,
            "seasons": [
                {"season_number": 1, "episode_count": 24},
                {"season_number": 2, "episode_count": 24},
            ],
        }
        mapper, patcher = _mapper(normal, None)
        try:
            assert mapper.map_auto(1396, 3, 1) is None
        finally:
            patcher.stop()

    def test_out_of_range_source_season_not_mapped(self):
        """源季号超过推断季数 → 跳过，避免误映射."""
        mapper, patcher = _mapper(MERGED_TMDB, [(1, 1, 24)])
        try:
            assert mapper.map_auto(220542, 3, 1) is None
        finally:
            patcher.stop()

    def test_explicit_season_high_episode_maps_through_inferred_block(self):
        """显式 S02E40 应按第二季起始集号累计到 S01E92."""
        mapper, patcher = _mapper(LONG_MERGED_TMDB, LONG_MERGED_BLOCKS)
        try:
            assert mapper.map_auto(226045, 2, 40, 43) == (1, 92, 1, 95)
        finally:
            patcher.stop()

    def test_no_season_still_uses_absolute_episode_mapping(self):
        """无季号的绝对 E78 直接归入 S01E78，不拆到其他季."""
        mapper, patcher = _mapper(MULTI_SEASON_TMDB, None)
        try:
            assert mapper.map_auto(1001, None, 78) == (1, 78)
        finally:
            patcher.stop()

    def test_existing_tmdb_season_maps_cumulatively_to_s01(self):
        """TMDB 已有 S02 时也累计归入 S01."""
        mapper, patcher = _mapper(MULTI_SEASON_TMDB, None)
        try:
            assert mapper.map_auto(1001, 2, 1, 3) == (1, 53, 1, 55)
        finally:
            patcher.stop()

    def test_explicit_season_outside_inferred_block_preserves_coordinates(self):
        """无法确定季块偏移时保留原值，避免生成重复集号."""
        mapper, patcher = _mapper(MERGED_TMDB, MERGED_BLOCKS)
        try:
            assert mapper.map_auto(220542, 2, 40, 43) is None
        finally:
            patcher.stop()
