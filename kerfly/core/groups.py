"""
Groups in groups: an element's group is a path of group ids, the outermost
first ("a1b2c3d4/e5f6a7b8": in group e5f6a7b8, which is in group a1b2c3d4).
A click on the bed takes the outermost group; a group picked in the element
list (the scope) is taken on its own.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""


def ids(group):
    return group.split("/") if group else []


def top(group):
    return group.split("/", 1)[0] if group else ""


def within(group, unit):
    """Is an element of `group` a member of the group `unit` (directly or in a group inside it)?"""
    return bool(unit) and (group == unit or group.startswith(unit + "/"))


def unit_of(group, scope=""):
    """The group that is selected together with an element of `group`: the scope when the element is in it,
    else the outermost group ("" for an element in no group)."""
    if not group:
        return ""
    if scope and within(group, scope):
        return scope
    return top(group)


def without(group, unit):
    """`group` with the level `unit` taken away (Ungroup): its members go to the group around it."""
    if not within(group, unit):
        return group
    parent = unit.rsplit("/", 1)[0] if "/" in unit else ""
    rest = group[len(unit):].lstrip("/")
    return "/".join(x for x in (parent, rest) if x)


def common(groups):
    """The innermost group all of `groups` are in ("" when none)."""
    paths = [ids(g) for g in groups]
    if not paths or any(not p for p in paths):
        return ""
    out = []
    for level in zip(*paths):
        if any(x != level[0] for x in level):
            break
        out.append(level[0])
    return "/".join(out)


def wrap(group, inside, new_id):
    """`group` put into a new group `new_id`, made inside the group `inside` (Group)."""
    if inside and within(group, inside):
        rest = group[len(inside):].lstrip("/")
        return "/".join(x for x in (inside, new_id, rest) if x)
    return "/".join(x for x in (new_id, group) if x)


def renamed(group, new_ids):
    """`group` with each id replaced by new_ids[id] (a copy of a group is a new group)."""
    return "/".join(new_ids[i] for i in ids(group))


def paths(group):
    """The group and every group around it, outermost first: "a/b/c" -> ["a", "a/b", "a/b/c"]."""
    parts = ids(group)
    return ["/".join(parts[:n]) for n in range(1, len(parts) + 1)]
