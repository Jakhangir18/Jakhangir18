import xml.etree.ElementTree as ET

import pytest

from scripts import climate, world

MOODS = [mood for _, _, mood in climate.BIOMES]


def state(mood="sunny", weeks=(0, 3, 0, 9), score=86, biome="Summer"):
    return climate.Climate(score, biome, mood, 0, 0, 0, 0, tuple(weeks))


def test_mix_endpoints_and_midpoint():
    assert world.mix("#000000", "#ffffff", 0) == "#000000"
    assert world.mix("#000000", "#ffffff", 1) == "#ffffff"
    assert world.mix("#102030", "#304050", .5) == "#203040"


def test_runs_merge_equal_neighbours():
    assert world.runs([2, 2, 5, 2, 2, 2]) == [(0, 2, 2), (2, 1, 5), (3, 3, 2)]


def test_trunk_is_absent_for_an_empty_week():
    assert world.trunk_height(0, 9) == 0
    assert world.trunk_height(0, 0) == 0


def test_trunk_grows_with_the_week():
    quiet, busy = world.trunk_height(1, 9), world.trunk_height(9, 9)
    assert 0 < quiet < busy == 90


def test_one_tree_per_week_with_contributions():
    svg = world.render(state(weeks=(0, 3, 0, 9, 1)), "light")
    assert svg.count('class="tree"') == 3
    assert "<title>9 contributions</title>" in svg


@pytest.mark.parametrize("mood", MOODS)
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_weather_is_well_formed_and_animated(mood, theme):
    svg = world.render(state(mood=mood), theme)
    root = ET.fromstring(svg)
    assert root.get("viewBox") == f"0 0 {world.W} {world.H}"
    assert f'class="{world.PARTICLE[mood]}"' in svg
    assert "prefers-reduced-motion" in svg


def test_label_and_title_carry_the_biome_and_score():
    svg = world.render(state(score=42, biome="Subtropics", mood="rain"), "light")
    assert ">Subtropics · 42/100</text>" in svg
    assert "Subtropics, score 42 of 100" in svg


def test_night_differs_and_has_stars():
    day, night = world.render(state(), "light"), world.render(state(), "dark")
    assert day != night
    assert night.count('fill="#ffffff" class="blink"') >= 46


def test_same_input_gives_the_same_picture():
    assert world.render(state(), "light") == world.render(state(), "light")


def test_a_year_without_contributions_still_draws():
    svg = world.render(state(mood="fog", weeks=(0,) * 26, score=0, biome="Dead Desert"), "light")
    assert 'class="tree"' not in svg and 'class="flag"' in svg


README = "intro\n<!-- world:start -->\nold\n<!-- world:end -->\nrest\n"


def test_rewrite_replaces_only_the_block():
    new = world.rewrite(README, state())
    assert new.startswith("intro\n<!-- world:start -->\n<picture>")
    assert new.endswith("</sub>\n<!-- world:end -->\nrest\n")
    assert "old" not in new and "<b>Summer, 86 of 100.</b>" in new


def test_rewrite_is_stable_when_nothing_changed():
    once = world.rewrite(README, state())
    assert world.rewrite(once, state()) == once


@pytest.mark.parametrize("text", ["no markers", README + README])
def test_rewrite_refuses_a_missing_or_doubled_block(text):
    with pytest.raises(SystemExit):
        world.rewrite(text, state())
