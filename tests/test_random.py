#!/usr/bin/env python3
"""
Random sessions (ROADMAP: release tests, step 4): many random steps in the real
window, with real mouse clicks and key presses, the way an impatient user
clicks around: draw, select, change a field to a random value, move, rotate,
group, combine, fill, cut hinges, undo, redo ... After every step the window
must tell the truth (kerfly.gui.truth) and each change must undo and redo
exactly.

The steps come from a seed, so a failure can be repeated exactly:

    QT_QPA_PLATFORM=xcb xvfb-run -a -s "-screen 0 1920x1080x24" \\
        .venv/bin/python tests/test_random.py --seed 7 --steps 300

On a failure the seed and the steps up to it are printed.

Copyright (C) 2026 Kerfly contributors
Licensed under the GNU General Public License v3 or later. See LICENSE.
"""
import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_release import MM, QApplication, QComboBox, QFontComboBox, QPlainTextEdit, QToolButton, Qt, \
    Session, truth  # noqa: E402

# sensible ranges for random numbers (a tiny pattern spacing on a big shape only makes the test slow)
RANGES = {"fill_spacing": (0.5, 8), "fill_angle": (-180, 180), "fill_margin": (0, 5), "hinge_cut": (5, 60),
          "hinge_gap": (1, 10), "hinge_spacing": (1.5, 10), "hinge_angle": (-180, 180), "hinge_margin": (0, 10),
          "hinge_band": (0, 80), "hinge_band_offset": (-30, 30), "tabs": (0, 6), "tab_width": (0.5, 5),
          "corner_radius": (0, 15), "sides": (3, 12), "font_size": (3, 30), "text_spacing": (-1, 5),
          "text_path_offset": (0, 80), "text_path_distance": (-3, 5)}
TOOLS = ("rectangle", "ellipse", "polygon", "line", "polyline", "pen", "freehand", "text")
WORDS = ("Kerfly", "K40", "laser", "Ab 12", "ŁÓDŹ", "x")


class RandomSession:
    def __init__(self, s, rnd):
        self.s = s
        self.w = s.w
        self.rnd = rnd
        self.log = []

    def point(self):
        return self.rnd.uniform(15, 300), self.rnd.uniform(15, 200)

    # ---------------------------------------------------------------- actions
    def draw(self):
        s, w, rnd = self.s, self.w, self.rnd
        tool = rnd.choice(TOOLS)
        x, y = self.point()
        dx, dy = rnd.uniform(8, 60), rnd.uniform(8, 45)
        mods = Qt.ShiftModifier if rnd.random() < 0.2 else Qt.NoModifier

        use_key = rnd.random() < 0.5

        def run():
            # the one-letter tool keys work while the bed view has the keyboard (not while typing in a field)
            on_bed = QApplication.focusWidget() is w.preview
            s.trigger(w.tool_actions[tool], via="key" if use_key and on_bed else "button")
            if tool == "polyline":
                for px, py in ((x, y), (x + dx, y), (x + dx / 2, y + dy)):
                    s.click_bed(px, py)
                s.click_bed(x, y)
            elif tool == "pen":
                s.click_bed(x, y)
                s.drag((x + dx, y), (x + dx + 5, y + dy / 2))
                s.click_bed(x + dx / 2, y + dy)
                s.click_bed(x, y)
            elif tool == "freehand":
                s.drag((x, y), (x + 1, y + 1), points=[(x + dx, y), (x + dx, y + dy), (x, y + dy)])
            elif tool == "text":
                s.click_bed(x, y)
            else:
                s.drag((x, y), (x + dx, y + dy), mods=mods)
            s.trigger(w.tool_actions["select"])
        return "draw %s at (%.0f, %.0f) %.0fx%.0f%s" % (tool, x, y, dx, dy, " Shift" if mods else ""), run, {}

    def select(self):
        s, w, rnd = self.s, self.w, self.rnd
        if not w.elements or rnd.random() < 0.15:
            return "click the empty bed", lambda: s.drag((1, 1), (2, 2)), {"change": False}
        e = rnd.choice(w.elements)
        mods = Qt.ControlModifier if rnd.random() < 0.3 else Qt.NoModifier
        x, y = s.element_at(e)
        return "click %s%s" % (e.name, " (Ctrl)" if mods else ""), lambda: s.click_bed(x, y, mods), {"change": False}

    def frame(self):
        x, y = self.point()
        x2, y2 = x + self.rnd.uniform(20, 150), y + self.rnd.uniform(20, 120)
        # starting on an element drags it instead of drawing a frame: either is fine
        return "frame (%.0f,%.0f)-(%.0f,%.0f)" % (x, y, x2, y2), lambda: self.s.drag((x, y), (x2, y2)), {"change": None}

    def field(self):
        s, rnd = self.s, self.rnd
        fields = truth.bar_fields(self.w.tool_options)
        if not fields:
            return None
        attr = rnd.choice(sorted(fields))
        widget = fields[attr]
        if isinstance(widget, QFontComboBox):
            value = widget.itemText(rnd.randrange(min(widget.count(), 40)))
        elif isinstance(widget, QComboBox):
            value = widget.itemData(rnd.randrange(widget.count()))
        elif isinstance(widget, QToolButton):
            value = not widget.isChecked()
        elif isinstance(widget, QPlainTextEdit):
            value = rnd.choice(WORDS)
        else:
            lo, hi = RANGES.get(attr, (widget.minimum(), min(widget.maximum(), widget.minimum() + 50)))
            value = rnd.uniform(lo, hi)
            if widget.decimals() if hasattr(widget, "decimals") else False:
                value = round(value, widget.decimals())
            else:
                value = int(round(value))
        if value == truth.shown_value(widget):
            return None
        return "options bar %s -> %r" % (attr, value), lambda: s.set_field(attr, value), {"change": None}

    def position(self):
        s, w, rnd = self.s, self.w, self.rnd
        if w.selected is None:
            return None
        key = rnd.choice(("x", "y", "w", "h", "rotation"))
        spin = w.sel_rotation if key == "rotation" else w.sel_fields[key]
        value = {"x": rnd.uniform(0, 250), "y": rnd.uniform(0, 170), "w": rnd.uniform(5, 80),
                 "h": rnd.uniform(5, 60), "rotation": rnd.choice((0, 15, 45, 90, -30, 180))}[key]
        return "type %s = %.2f" % (key, value), lambda: s.type_number(spin, value), {"change": None}

    def move(self):
        s, w, rnd = self.s, self.w, self.rnd
        if not w.elements:
            return None
        e = rnd.choice(w.elements)
        x, y = s.element_at(e)
        dx, dy = rnd.uniform(-40, 40), rnd.uniform(-30, 30)
        if rnd.random() < 0.5:
            return "drag %s by (%.0f, %.0f)" % (e.name, dx, dy), lambda: s.drag((x, y), (x + dx, y + dy)), {"change": None}
        key = rnd.choice((Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down))
        mods = Qt.ShiftModifier if rnd.random() < 0.4 else Qt.NoModifier
        return "arrow key %s%s" % (key, " Shift" if mods else ""), lambda: (s.click_bed(x, y), s.key(key, mods)), \
            {"change": None}

    def command(self):
        s, w, rnd = self.s, self.w, self.rnd
        if not w.elements:
            return None
        pool = [w.act_rot_left, w.act_rot_right, w.act_mirror_h, w.act_mirror_v, w.act_duplicate, w.act_delete,
                w.act_center, w.act_group, w.act_ungroup, w.act_text_path] + list(w.act_align.values()) + \
            [w.act_distribute_h, w.act_distribute_v] + list(w.act_order.values()) + list(w.act_boolean.values())
        action = rnd.choice(pool)
        via = rnd.choice(("button", "menu", "key")) if not action.shortcut().isEmpty() else rnd.choice(("button", "menu"))
        bed_only = action.shortcutContext() == Qt.WidgetWithChildrenShortcut     # e.g. PgUp: only on the bed
        if via == "key" and bed_only:
            via = "bed key"
        if action is w.act_delete:
            via = rnd.choice(("menu", "key"))
            if via == "key":                          # Del works while the bed view has the keyboard
                return "Delete (Del)", lambda: (s.click_bed(*s.element_at(w.selected or w.elements[0])),
                                                s.key(Qt.Key_Delete)), {"change": None}
        def run():
            how = via
            if how == "bed key":
                how = "key" if QApplication.focusWidget() is w.preview else "menu"
            s.trigger(action, via=how)
        return "%s (%s)" % (action.text().replace("&", ""), via), run, {"change": None}

    def tool_click(self):
        s, w, rnd = self.s, self.w, self.rnd
        if not w.elements:
            return None
        tool = rnd.choice(("fill", "hinge", "textpath"))
        e = rnd.choice(w.elements)
        x, y = s.element_at(e)

        def run():
            s.trigger(w.tool_actions[tool])
            s.click_bed(x, y)
            s.trigger(w.tool_actions["select"])
        return "%s tool: click %s" % (tool, e.name), run, {"change": None}

    def layer(self):
        s, w, rnd = self.s, self.w, self.rnd
        combos = [c for c in w.layer_assign_box.findChildren(QComboBox) if s.on_screen(c)]
        if not combos:
            return None
        row = rnd.randrange(len(combos))
        index = rnd.randrange(combos[row].count())
        name = combos[row].itemText(index)

        def run():                                     # the list as it is now (a change rebuilds them)
            now = [c for c in w.layer_assign_box.findChildren(QComboBox) if s.on_screen(c)]
            now.sort(key=lambda c: c.mapTo(w, c.rect().topLeft()).y())
            combo = now[min(row, len(now) - 1)]
            target = combo.findText(name)
            if target >= 0:
                s.pick(combo, index=target)
        return "Layer list %d -> %s" % (row + 1, name), run, {"change": None}

    def tick(self):
        s, w, rnd = self.s, self.w, self.rnd
        if not w.elements:
            return None
        row = rnd.randrange(len(w.elements))
        lst = w.element_list

        def run():
            r = lst.visualItemRect(lst.item(row))
            from test_release import QPoint, QTest
            QTest.mouseClick(lst.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(r.left() + r.height() // 2,
                                                                                    r.center().y()))
            s.settle()
        return "element list: tick / untick row %d" % (row + 1), run, {}

    def undo_redo(self):
        s, w = self.s, self.w
        action = self.rnd.choice((w.act_undo, w.act_redo))
        if not action.isEnabled():
            return None
        return action.text().replace("&", ""), lambda: s.trigger(action), {"undo": False, "change": None}

    WEIGHTS = (("draw", 14), ("select", 14), ("frame", 5), ("field", 22), ("position", 8), ("move", 10),
               ("command", 14), ("tool_click", 6), ("layer", 4), ("tick", 3), ("undo_redo", 6))

    def next_step(self):
        names = [n for n, _w in self.WEIGHTS]
        weights = [wt for _n, wt in self.WEIGHTS]
        if len(self.w.elements) > 14:                   # keep the bed from filling up
            return "Delete all (frame + Del)", self._clear, {"change": None}
        for _attempt in range(20):
            made = getattr(self, self.rnd.choices(names, weights)[0])()
            if made is not None:
                return made
        return self.select()

    def _clear(self):
        s, w = self.s, self.w
        s.trigger(w.tool_actions["select"])
        s.drag((1, 1), (320, 215))
        s.trigger(w.act_delete, via="menu")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--steps", type=int, default=300)
    parser.add_argument("--runs", type=int, default=1, help="several seeds, one after the other")
    args = parser.parse_args()
    app = QApplication(sys.argv)
    seeds = [args.seed] if args.seed is not None else [int(time.time()) % 100000 + n for n in range(args.runs)]
    if args.seed is not None and args.runs > 1:
        seeds = [args.seed + n for n in range(args.runs)]
    failed = 0
    for seed in seeds:
        s = Session(app)
        s.quiet = True
        rnd = random.Random(seed)
        r = RandomSession(s, rnd)
        t0 = time.time()
        for n in range(args.steps):
            name, run, options = r.next_step()
            r.log.append(name)
            before = len(s.failures)
            s.step("[seed %d, step %d] %s" % (seed, n + 1, name), run, **options)
            if len(s.failures) > before:
                print("\nRandom session FAILED (seed %d, step %d). Steps up to it:" % (seed, n + 1))
                for k, line in enumerate(r.log):
                    print("  %3d. %s" % (k + 1, line))
                print("Repeat with: tests/test_random.py --seed %d --steps %d" % (seed, n + 1))
                failed += 1
                break
        else:
            print("seed %d: %d random steps, all fine (%.0f s)" % (seed, args.steps, time.time() - t0))
        s.w._dirty = False
        s.w.close()
        s._dialog_timer.stop()
    print("Random sessions: %d of %d failed" % (failed, len(seeds)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
