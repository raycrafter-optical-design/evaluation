"""Tests for the text-level Zemax fixes, using a tiny synthetic ``.zmx``."""

import re

from evaluation_tools.zemax_text import (
    apply_pickups,
    configuration_values,
    expand_surface_tilts,
    galvo_surface_index,
    set_galvo_angle,
    split_surfaces,
)

SYNTHETIC = """VERS 1
UNIT MM
SURF 0
  TYPE STANDARD
  DISZ INFINITY
SURF 1
  TYPE COORDBRK
  PARM 3 3
  PARM 4 0
  DISZ 0
SURF 2
  TYPE STANDARD
  GLAS MIRROR 0 0
  DISZ 0
SURF 3
  TYPE COORDBRK
  PARM 3 -3
  PPAR 3 1 -1.0 0.0 0
  DISZ 5
SURF 4
  TYPE STANDARD
  SCBD 1 0 0 0.0 -0.37 45.0 0.0 0.0
  DISZ 1.1
SURF 5
  TYPE STANDARD
  SCBD 2 0 0 0.0 0.0 -45.0 0.0 0.0
  DISZ 50
BLNK
PRAM   3   1 3.0 0 3 0 1
PRAM   3   2 -10.0 0 3 0 1
"""


def test_split_keeps_tail_apart_from_the_last_surface():
    _, blocks, tail = split_surfaces(SYNTHETIC)
    assert len(blocks) == 6
    assert tail.startswith("BLNK")
    assert "BLNK" not in blocks[-1]


def test_configuration_values_lists_prams_in_order():
    assert configuration_values(SYNTHETIC) == [3.0, -10.0]


def test_galvo_surface_is_the_pickup_source():
    assert galvo_surface_index(SYNTHETIC) == 1


def test_pickup_follows_the_source_value():
    _, blocks, _ = split_surfaces(set_galvo_angle(SYNTHETIC, 7.0))
    assert re.search(r"PARM 3 7.0", blocks[1])
    assert re.search(r"PARM 3 -7.0", blocks[3])  # -1 times the galvo angle


def test_apply_pickups_leaves_blocks_without_pickups_alone():
    _, blocks, _ = split_surfaces(SYNTHETIC)
    assert apply_pickups(blocks)[0] == blocks[0]


def test_surface_tilts_become_coordinate_breaks_in_the_right_place():
    _, blocks, _ = split_surfaces(expand_surface_tilts(SYNTHETIC))
    types = [re.search(r"TYPE (\w+)", b).group(1) for b in blocks]
    # mode 1 puts a break before surface 4; mode 2 puts one after surface 5
    assert types == [
        "STANDARD",
        "COORDBRK",
        "STANDARD",
        "COORDBRK",
        "COORDBRK",
        "STANDARD",
        "STANDARD",
        "COORDBRK",
    ]
    assert not re.search(r"(?m)^\s+SCBD ", "".join(blocks))  # only the comment mentions it
    assert re.search(r"PARM 2 -0.37", blocks[4]) and re.search(r"PARM 3 45.0", blocks[4])
    # the mode 2 break carries the surface's thickness and the surface itself none
    assert re.search(r"DISZ 50.0", blocks[7]) and re.search(r"DISZ 0.0", blocks[6])


def test_surfaces_are_renumbered_after_insertion():
    expanded = expand_surface_tilts(SYNTHETIC)
    numbers = [int(n) for n in re.findall(r"(?m)^SURF (\d+)", expanded)]
    assert numbers == list(range(len(numbers)))
