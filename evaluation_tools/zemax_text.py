"""Text-level fixes for Zemax features that Optiland 0.6.3 silently ignores.

Optiland's Zemax reader skips three things the TWINKLE designs rely on. Each has an issue entry
in ``optiland_issues_found.md``. Here we rewrite the (UTF-8) ``.zmx`` text before it is loaded:

* ``SCBD``: a tilt/decenter attached to an ordinary surface (the tilted dichroic). We turn it
  into an explicit ``COORDBRK`` surface placed in front of that surface.
* ``PPAR``: a parameter pickup (the galvo return tilt is minus the galvo tilt). We re-evaluate
  the pickups after the file has been edited.
* ``MNUM`` / ``PRAM``: multi-configuration data (the galvo angle). Optiland loads configuration 1
  only. We list the configuration values and write any one of them into the text.

The multi-configuration operand is not named in the file in a form we can decode, so
:func:`galvo_surface_index` assumes it is parameter 3 (tilt about x) of the surface that other
surfaces pick up from. That matches the Zemax API script in the TWINKLE repository.
"""

from __future__ import annotations

import re

SURFACE_START = re.compile(r"(?m)^(?=SURF \d+)")
TAIL_START = re.compile(r"(?m)^(?=DMFS|BLNK|MNCA|TOL |MNUM)")


def split_surfaces(text: str) -> tuple[str, list[str], str]:
    """Split ``.zmx`` text into ``(header, surface_blocks, tail)``.

    The tail holds everything after the last surface (merit function, tolerances, multi-config
    data), which Optiland does not need but which must be written back unchanged.
    """
    header, *blocks = SURFACE_START.split(text)
    last_block, *rest = TAIL_START.split(blocks[-1], maxsplit=1)
    blocks[-1] = last_block
    return header, blocks, rest[0] if rest else ""


def join_surfaces(header: str, blocks: list[str], tail: str) -> str:
    """Inverse of :func:`split_surfaces`, renumbering the ``SURF n`` lines from zero."""
    numbered = [re.sub(r"^SURF \d+", f"SURF {i}", block) for i, block in enumerate(blocks)]
    return header + "".join(numbered) + tail


def _get_parameter(block: str, name: str) -> float | None:
    """Value of a ``PARM n`` line (``name`` is e.g. ``"PARM 3"``) in a surface block."""
    match = re.search(rf"(?m)^\s+{name} (\S+)", block)
    return float(match.group(1)) if match else None


def _set_parameter(block: str, name: str, value: float) -> str:
    """Replace the value of a ``PARM n`` line, if the block has one."""
    return re.sub(rf"(?m)^(\s+{name} )\S+", lambda m: f"{m.group(1)}{value!r}", block, count=1)


def _block_type(block: str) -> str:
    match = re.search(r"(?m)^\s+TYPE (\w+)", block)
    return match.group(1) if match else ""


# ------------------------------------------------------------------ pickups ---
def galvo_surface_index(text: str) -> int | None:
    """Index of the surface whose tilt the multi-configuration table drives.

    This is the source of the first ``PPAR 3 <source> ...`` pickup, i.e. the coordinate break
    that another break copies its x tilt from. Returns None when there are no such pickups.
    """
    match = re.search(r"(?m)^\s+PPAR 3 (\d+) ", text)
    return int(match.group(1)) if match else None


def apply_pickups(blocks: list[str]) -> list[str]:
    """Re-evaluate ``PPAR <param> <source surface> <scale> <offset>`` pickups, in surface order."""
    blocks = list(blocks)
    for index, block in enumerate(blocks):
        for match in re.finditer(r"(?m)^\s+PPAR (\d) (\d+) (\S+) (\S+)", block):
            parameter, source, scale, offset = int(match[1]), int(match[2]), match[3], match[4]
            source_value = _get_parameter(blocks[source], f"PARM {parameter}")
            if source_value is not None:
                new_value = float(scale) * source_value + float(offset)
                blocks[index] = _set_parameter(blocks[index], f"PARM {parameter}", new_value)
    return blocks


# ------------------------------------------------------------ configurations ---
def configuration_values(text: str) -> list[float]:
    """Operand values of every configuration, from the ``PRAM`` lines (empty if single-config)."""
    return [float(line.split()[3]) for line in text.splitlines() if line.startswith("PRAM")]


def set_galvo_angle(text: str, angle_deg: float) -> str:
    """Return ``text`` with the galvo tilt set to ``angle_deg`` and the pickups re-evaluated."""
    galvo = galvo_surface_index(text)
    if galvo is None:
        raise ValueError("no PPAR pickups found, so the galvo surface is unknown")
    header, blocks, tail = split_surfaces(text)
    blocks[galvo] = _set_parameter(blocks[galvo], "PARM 3", angle_deg)
    return join_surfaces(header, apply_pickups(blocks), tail)


# ------------------------------------------------------------------- SCBD ---
def expand_surface_tilts(text: str) -> str:
    """Turn each ``SCBD`` (surface tilt/decenter) into a ``COORDBRK`` surface.

    ``SCBD mode a b dx_mm dy_mm tilt_x_deg tilt_y_deg tilt_z_deg``. Mode 1 is a tilt applied
    *before* the surface: a break is inserted in front of it. Mode 2 is applied *after* the
    surface: a break is inserted behind it and takes over the surface's thickness, so the
    next surface is placed along the returned axis. Together they tilt a plate (both faces
    tilted, axis restored afterwards), which is how the TWINKLE dichroic is modelled.

    The mode meaning is inferred from the dichroic, where a +45 degree mode-1 tilt is followed
    by a -45 degree mode-2 tilt on the back face; it reproduces Zemax's stored semi-diameters.
    """
    header, blocks, tail = split_surfaces(text)
    expanded: list[str] = []
    for block in blocks:
        match = re.search(r"(?m)^\s+SCBD (\S+) \S+ \S+ (\S+) (\S+) (\S+) (\S+) (\S+)", block)
        if not match:
            expanded.append(block)
            continue
        mode = int(match.group(1))
        dx, dy, tilt_x, tilt_y, tilt_z = (float(value) for value in match.groups()[1:])
        block = re.sub(r"(?m)^\s+SCBD .*\n", "", block)
        if mode == 1:
            expanded.append(_coordinate_break_block(dx, dy, tilt_x, tilt_y, tilt_z, 0.0))
            expanded.append(block)
        else:
            thickness = _get_parameter(block, "DISZ") or 0.0
            expanded.append(_set_parameter(block, "DISZ", 0.0))
            expanded.append(_coordinate_break_block(dx, dy, tilt_x, tilt_y, tilt_z, thickness))
    return join_surfaces(header, expanded, tail)


def _coordinate_break_block(
    dx: float, dy: float, tx: float, ty: float, tz: float, thickness_mm: float
) -> str:
    """A minimal ``COORDBRK`` surface block (order 0: decenter, then tilt x, y, z), then move on."""
    return (
        "SURF 0\n  COMM tilt/decenter expanded from SCBD\n  TYPE COORDBRK\n"
        f"  PARM 1 {dx!r}\n  PARM 2 {dy!r}\n  PARM 3 {tx!r}\n  PARM 4 {ty!r}\n"
        f'  PARM 5 {tz!r}\n  PARM 6 0\n  DISZ {thickness_mm!r}\n  DIAM 0 0 0 0 1 ""\n'
    )
