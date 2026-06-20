"""Tests for palette definitions."""
from app.palettes import NAMED_PALETTES, flatten, palette_names


def test_palette_names_include_adaptive():
    names = palette_names()
    assert names[0] == "adaptive"
    assert "nes" in names
    assert "gameboy" in names


def test_flatten_length():
    pal = NAMED_PALETTES["gameboy"]
    flat = flatten(pal)
    assert len(flat) == len(pal) * 3
    assert all(0 <= v <= 255 for v in flat)


def test_all_palettes_are_rgb_triples():
    for name, pal in NAMED_PALETTES.items():
        assert len(pal) >= 2, name
        for color in pal:
            assert len(color) == 3, name
            assert all(0 <= c <= 255 for c in color), name
