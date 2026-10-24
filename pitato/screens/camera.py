"""The Camera tab: your cameras, one camera's picture, and the bot saying what it sees."""
import time

from ..theme import ACCENT, BG, BODY, MUTED, ROW, TEXT, WARN
from ..net import cam_address, cam_host, cam_key
from ..library import LIBRARY
from ..cameras import CAM_SHOT_SHOW, edit_cameras, read_cameras, turn_picture
from ..bot import friend_face


class CameraScreen:
    """The Camera tab: your cameras, one camera's picture, and the bot saying what it sees."""

    def on_camera_page(self):
        """A camera's live picture is on screen."""
        return self.active and self.view == "list" and self.tab_type() == "camera" and not self.cam_list

    def on_camera_list(self):
        return self.active and self.view == "list" and self.tab_type() == "camera" and self.cam_list

    def camera_changed(self):
        """A new picture or camera state arrived (from the camera's threads)."""
        if self.on_camera_page() or self.on_camera_list():
            self.dirty = True
        if self.on_camera_list() and not self.camera.scanning and self.camera.unseen():
            self.camera.scan()                       # one just heard on the network, say

    def pie_cameras(self):
        """(cameras that answered as PiE-ink, the addresses in camera.txt: a PiE-ink's camera is at the
        Pi's address, so one of them may be a PiE-ink)."""
        cam = self.camera
        sure = [v["url"] for v in list(cam.known.values()) if v.get("kind") == "pie" and v.get("server") == "PiE-ink"]
        return sure, [c["addr"] for c in cam.cams or read_cameras(LIBRARY[self.tab_index("camera")]["files"])]

    def press_cameras(self, name, repeat):
        """The Camera tab: the live picture (B for your cameras, L R between them), or the list."""
        cam = self.camera
        if not self.cam_list:
            if name == "b":
                if not repeat:
                    self.camera_list()
                return None
            place = cam.place()
            if name in ("l", "r") and place and place[1] > 1:
                if not repeat:
                    self.camera_step(1 if name == "r" else -1)
                return None
            if name in ("l", "r"):
                return "pass"
            if name == "y" and not cam.steers:        # (one that turns: Y zooms; its list turns it)
                if cam.addr and not repeat:
                    self.camera_turn(cam.addr)
                return None
            if name == "select" and not cam.steers:   # (one that turns: when SELECT is let go)
                if cam.addr and not repeat:
                    self.camera_select()
                return None
            if cam.addr and not repeat:
                cam.press(name)
                self.dirty = True
            return None
        rows = self.cam_rows()
        n = len(rows)
        sel = max(0, min(self.cam_sel, n - 1))
        if name in ("up", "down"):
            step = 1 if name == "down" else -1
            sel = (sel + step) % n
            if rows[sel][0] == "label":
                sel = (sel + step) % n
            self.cam_sel = sel
            self.confirm = (None, 0.0)
        elif name == "a" and not repeat:
            kind, entry = rows[sel]
            if kind == "add":
                self.open_keyboard("Camera address (192.168.1.50, or a link)", "", self.camera_typed,
                                   row=0, limit=120)
            elif kind == "found":
                self.camera_add(entry["addr"], entry["name"])
            elif kind == "cam":
                self.camera_open(entry["addr"])
        elif name == "y" and not repeat and rows[sel][0] == "cam":
            self.camera_turn(rows[sel][1]["addr"])
        elif name in ("left", "right") and not repeat and rows[sel][0] == "cam":
            self.camera_flip(rows[sel][1]["addr"])
        elif name == "x" and not repeat and rows[sel][0] == "cam":
            entry = rows[sel][1]
            key = "camdel:" + cam_key(entry["addr"])
            if self.confirm[0] == key:
                self.confirm = (None, 0.0)
                self.camera_remove(entry["addr"])
            else:
                self.confirm = (key, time.monotonic() + 4)
                self.toast(f"Press X again to remove {cam.name_of(entry['addr'])}", 4)
        elif name in ("l", "r", "b"):
            return "pass"
        self.dirty = True
        return None

    def camera_select(self):
        """SELECT on a camera's picture (let go quickly, on one that turns): the bot says what it
        sees, or stops talking. With no bot, what it did before: the next speed."""
        cam = self.camera
        if not self.friend.ready():
            if cam.steers:
                cam.next_speed()
            else:
                cam.press("select")
        elif self.voice.speaking:
            self.voice.stop()
        elif self.friend.busy:
            self.toast("Still looking" if (self.cam_bot or {}).get("busy")
                       else "Still thinking about the last one", 2)
        else:
            ok, why = self.camera_describe(cam.addr)
            if not ok:
                self.toast(why, 3)
        self.dirty = True

    def camera_describe(self, addr):
        """The bot looks through one of your cameras and says what it sees: out loud with a voice, and
        over the picture when that camera is on screen. (True, "") or (False, why not)."""
        fr = self.friend
        if not fr.ready():
            return False, "Set up your bot first: Settings > Bot"
        if not addr:
            return False, "Pick a camera first"
        was, token = self.cam_bot, object()
        self.cam_bot = {"addr": addr, "busy": True, "text": "", "note": "", "error": False, "spoken": False,
                        "until": 0.0, "token": token}
        if not fr.describe(lambda: self.camera_look(addr),
                           lambda text, error: self.camera_described(token, text, error)):
            self.cam_bot = was
            return False, "Still thinking about the last one"
        self.dirty = True
        return True, ""

    def camera_look(self, addr):
        """A picture from a camera for the bot: (its JPEG, the camera) or (None, why not). The one on
        screen: just what's on screen. Turned as its picture is (the bot sees it the right way up)."""
        cam = self.camera
        name = cam.name_of(addr)
        jpeg = cam.jpeg
        if cam_key(addr) == cam_key(cam.addr) and jpeg is not None and time.monotonic() - cam.frame_at < 5:
            return cam.turned_file(addr, jpeg), name
        got = cam.snapshot(addr, max_age=2)
        return (cam.turned_file(addr, got[0], got[2]), name) if got else (None, f"the camera {name} didn't answer")

    def camera_turn(self, addr):
        """A camera's picture turned a quarter clockwise (a camera on its side), kept for next time: on
        the screen, its photos, what the bot sees, and on the web page. How far it's turned now."""
        cam = self.camera
        deg = (cam.turn_of(addr) + 90) % 360
        cam.set_turn(addr, deg)
        self.save_state()
        self.toast(f"{cam.name_of(addr)}: turned {deg}°" if deg else f"{cam.name_of(addr)}: not turned", 2)
        self.dirty = True
        return deg

    def camera_flip(self, addr):
        """One that turns the wrong way (right when ◀ is pressed): left and right swapped as it's steered, kept
        for next time; or back as they were. Whether they're swapped now (None: it doesn't turn)."""
        cam = self.camera
        if not cam.may_steer(addr):
            self.toast("This camera doesn't turn", 2)
            return None
        on = not cam.flipped(addr)
        cam.set_flip(addr, on)
        self.save_state()
        self.toast(f"{cam.name_of(addr)}: left and right swapped" if on
                   else f"{cam.name_of(addr)}: left and right as normal", 2)
        self.dirty = True
        return on

    def camera_described(self, token, text, error):
        """It said what it sees (on its own thread): out loud too, and over the picture for a while."""
        told = self.cam_bot
        if not told or told["token"] is not token:
            return
        note, spoken = "", False
        if text and not error:
            spoken, why = self.say_aloud(text)
            note = "" if spoken else why
        said = error or text or ""
        self.cam_bot = dict(told, busy=False, text=said, error=bool(error), note=note, spoken=spoken,
                            until=time.monotonic() + max(8.0, 4 + len(said) / 12))
        self.dirty = True

    def camera_list(self):
        """Your cameras, with a small picture of each."""
        cam = self.camera
        cam.stop()
        self.cam_list = True
        rows = self.cam_rows()
        self.cam_sel = next((i for i, (k, e) in enumerate(rows)
                             if k == "cam" and cam_key(e["addr"]) == cam_key(cam.addr)), 0)
        cam.scan()
        self.dirty = True

    def camera_open(self, addr):
        """One camera's live picture."""
        cam = self.camera
        cam.select(addr)
        self.state["camera"] = addr
        self.save_state()
        self.cam_list = False
        if self.on_camera_page():
            cam.start()
        self.dirty = True

    def camera_step(self, d):
        cam = self.camera
        place = cam.place()
        if not place:
            return
        nxt = cam.cams[(place[0] - 1 + d) % place[1]]["addr"]
        cam.stop()
        self.camera_open(nxt)

    def camera_typed(self, text):
        addr = cam_address(text)
        if not addr:
            self.toast("That isn't an address. Try 192.168.1.50, or a link", 4)
            return
        self.camera_add(addr, "")

    def camera_add(self, addr, name=""):
        """A camera into camera.txt (for good), and on screen."""
        cam = self.camera
        if not cam.mine(addr):
            try:
                edit_cameras(add=addr, name=name)
            except OSError as ex:
                self.toast(f"Couldn't save it ({ex.strerror or ex})", 4)
                return
            cam.load(cam.patterns or LIBRARY[self.tab_index("camera")]["files"], last=addr)
            self.toast(f"Added {name or addr}", 3)
        self.camera_open(addr)

    def camera_remove(self, addr):
        cam = self.camera
        name = cam.name_of(addr)
        try:
            edit_cameras(remove=addr)
        except OSError as ex:
            self.toast(f"Couldn't change static/camera.txt ({ex.strerror or ex})", 4)
            return
        was = cam_key(addr) == cam_key(cam.addr)
        cam.cams = read_cameras(cam.patterns or LIBRARY[self.tab_index("camera")]["files"])
        if cam.turn_of(addr) or cam.flipped(addr):    # (added again later: the right way up, steered as it is)
            cam.set_turn(addr, 0)
            cam.set_flip(addr, False)
            self.save_state()
        if was:
            cam.select(cam.cams[0]["addr"] if cam.cams else "")
            if self.state.get("camera") and cam_key(self.state["camera"]) == cam_key(addr):
                self.state.pop("camera", None)
                self.save_state()
        self.toast(f"Removed {name}", 3)
        self.dirty = True

    def picture_saved(self, path):
        """A picture from the Camera tab landed in ~/Pictures (None: it didn't)."""
        if path is None:
            if self.msg == "Saved to Pictures":
                self.msg = None
            return
        self.last_shot = path
        if self.on_camera_page():
            self.toast("Saved to Pictures", 3)

    def render_camera(self):
        from PIL import Image
        F = self.fonts
        cam = self.camera
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        top, bottom = self.HEADER + 1, H - self.FOOTER
        AW, AH = W, bottom - top
        if not cam.addr:
            self.empty_state(d, "No camera chosen", "Press B to pick one or add one")
            self.footer(d, [("B", "Cameras")])
            self.fb.show(img)
            return

        frame = cam.frame
        if frame is not None:                       # the live picture, as big as it fits
            s = min(AW / frame.width, AH / frame.height)
            size = (max(int(frame.width * s), 1), max(int(frame.height * s), 1))
            pic = frame if size == frame.size else frame.resize(size, Image.BILINEAR)
            img.paste(pic, ((AW - size[0]) // 2, top + (AH - size[1]) // 2))
        else:
            mid = top + AH / 2
            cx, cy = W / 2, mid - 40
            d.rounded_rectangle((cx - 44, cy - 40, cx + 44, cy + 40), radius=16, fill=ROW)
            d.ellipse((cx - 24, cy - 24, cx + 24, cy + 24), fill=BG, outline=ACCENT, width=3)
            d.ellipse((cx - 7, cy - 7, cx + 7, cy + 7), fill=ACCENT)
            if cam.reached is False:
                big, small = "Can't reach this camera", f"Is it on? Nothing answered at {cam.where}"
            elif cam.kind == "pie" and cam.info and not cam.available:
                big, small = "No picture from that Pi", "Is its camera plugged in?"
            else:
                big, small = "Connecting", cam.where
            d.text((W / 2, mid + 30), big, font=F["big"], fill=TEXT, anchor="mm")
            d.text((W / 2, mid + 60), self.fit(d, small, F["small"], W - 40), font=F["small"],
                   fill=MUTED, anchor="mm")

        told = self.cam_bot                         # what the bot says it sees (SELECT)
        if told and cam_key(told["addr"]) == cam_key(cam.addr) and (told["busy"]
                                                                  or time.monotonic() < told["until"]):
            self.camera_told(d, told, bottom)

        # arrows on the picture's edges light up while it turns
        if cam.steers:
            arrows = {"up": (W / 2, top + 22, "▲"), "down": (W / 2, bottom - 22, "▼"),
                      "left": (22, top + AH / 2, "◀"), "right": (W - 22, top + AH / 2, "▶")}
            for k, (ax, ay, glyph) in arrows.items():
                on = k in cam.held
                if on or frame is None:
                    d.ellipse((ax - 15, ay - 15, ax + 15, ay + 15), fill=ACCENT if on else ROW)
                    d.text((ax, ay), glyph, font=F["small"], fill=BG if on else MUTED, anchor="mm")

        # a little status card over the corner of the picture
        bits = []
        if cam.zoom is not None and cam.available:
            bits.append(f"Zoom {round(cam.zoom * 100)}%")
        if cam.speed != "normal" and cam.steers:
            bits.append(cam.speed.capitalize())
        if cam.following:
            bits.append("Following you")
        if cam.asleep:
            bits.append("Asleep")
        now = time.monotonic()
        if cam.action != self.cam_said[0]:
            self.cam_said = (cam.action, now)
        busy = cam.held or cam.zoom_dir or cam.shooting
        keep = 6 if cam.action.startswith("No picture") else 3
        action = cam.action if busy or now - self.cam_said[1] < keep else ""
        text = action or "   ".join(bits)
        if text:
            tw = d.textlength(text, font=F["small"]) + 28
            d.rounded_rectangle((12, top + 10, 12 + tw, top + 40), radius=15, fill=BG)
            d.text((26, top + 25), text, font=F["small"], fill=ACCENT if action else BODY,
                   anchor="lm")
        shot = cam.shot                             # the picture just taken, in the corner
        if shot and time.monotonic() - shot[2] < CAM_SHOT_SHOW:
            small = shot[0]
            x1, y0 = W - 14, top + 12
            x0 = x1 - small.width
            d.rounded_rectangle((x0 - 5, y0 - 5, x1 + 5, y0 + small.height + 5), radius=8, fill=TEXT)
            img.paste(small, (int(x0), int(y0)))

        # which camera this is, bottom left, with L R between yours when there are more
        # (out of the way while a notice is up there)
        place = cam.place()
        tag = f"{place[0]} of {place[1]}" if place and place[1] > 1 else ""
        if not self.msg:
            name = self.fit(d, cam.title, F["small_b"], W // 2)
            y = bottom - 26
            w = d.textlength(name, font=F["small_b"]) + (d.textlength(tag, font=F["small"]) + 76 if tag else 0)
            d.rounded_rectangle((12, y - 15, 12 + w + 28, y + 15), radius=15, fill=BG)
            x = 26
            if tag:
                x = self.key(d, x, y, "L") + 8
            d.text((x, y), name, font=F["small_b"], fill=TEXT, anchor="lm")
            x += d.textlength(name, font=F["small_b"]) + 12
            if tag:
                d.text((x, y), tag, font=F["small"], fill=MUTED, anchor="lm")
                x += d.textlength(tag, font=F["small"]) + 8
                self.key(d, x, y, "R")

        # SELECT: the bot says what it sees, when there's one (on one that turns, holding START
        # then sets the speed, which SELECT did before); a lit key: on
        bot = ("SEL", "Stop" if self.voice.speaking else "Describe") if self.friend.ready() else None
        if cam.steers:
            hints = [("X Y", "Zoom"), ("A", "Taking…" if cam.shooting else "Photo"),
                     ("START", "Home"), bot or ("SEL", "Speed")]
            if cam.can_follow:
                hints.append(("Hold SEL", "Follow", cam.following))
            else:
                hints.append(("B", "Cameras"))
        else:
            hints = [("A", "Taking…" if cam.shooting else "Photo"), ("Y", "Rotate")] + ([bot] if bot else []) \
                + [("B", "Cameras")]
            if not tag:
                hints.append(("L R", "Tabs"))
        self.footer(d, hints)
        self.fb.show(img)

    def camera_told(self, d, told, bottom):
        """What the bot said it sees, across the foot of the picture, with its face; or that it's
        looking. (Above which camera this is.)"""
        F, W = self.fonts, self.fb.w
        busy = told["busy"]
        face = friend_face(told["text"], "error" if told["error"] else "", busy)[0]
        fw = d.textlength(face, font=F["small"])
        tw = W - 24 - 28 - fw - 12
        lines = ["Looking…"] if busy else self.wrap(d, told["text"], F["small"], tw, 4)
        note = "" if busy else self.fit(d, told["note"], F["small"], tw)
        y1 = bottom - 52
        y0 = y1 - (20 + 21 * len(lines) + (21 if note else 0))
        d.rounded_rectangle((12, y0, W - 12, y1), radius=14, fill=BG)
        d.text((26, y0 + 10), face, font=F["small"], fill=ACCENT, anchor="la")
        x, y = 26 + fw + 12, y0 + 10
        for line in lines:
            d.text((x, y), line, font=F["small"], fill=BODY if busy else TEXT, anchor="la")
            y += 21
        if note:
            d.text((x, y), note, font=F["small"], fill=MUTED, anchor="la")

    def cam_rows(self):
        """The Camera tab's list: your cameras, a row to add one, then the ones on the network."""
        cam = self.camera
        rows = [("cam", c) for c in cam.cams] + [("add", None)]
        found = cam.found_list()
        if found:
            rows.append(("label", "On your network"))
            rows += [("found", f) for f in found]
        return rows

    def render_cameras(self):
        F = self.fonts
        cam = self.camera
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        rows = self.cam_rows()
        n = len(rows)
        if rows[min(self.cam_sel, n - 1)][0] == "label":
            self.cam_sel += 1
        sel = self.cam_sel = max(0, min(self.cam_sel, n - 1))
        d.text((20, self.LIST_TOP + 10), "Your cameras" if cam.cams else "No cameras yet",
               font=F["small"], fill=MUTED, anchor="lm")
        if cam.scanning:
            d.text((W - 20, self.LIST_TOP + 10), "Looking at them…", font=F["small"], fill=MUTED, anchor="rm")
        top_y = self.LIST_TOP + 28
        shown = max(1, (H - self.FOOTER - top_y) // self.ROW_H)
        top = self.tops.get("cameras", 0)
        top = sel if sel < top else (sel - shown + 1 if sel >= top + shown else top)
        top = max(0, min(top, n - shown))
        self.tops["cameras"] = top
        x0, x1 = 12, W - 22
        for r, i in enumerate(range(top, min(top + shown, n))):
            kind, entry = rows[i]
            y = top_y + r * self.ROW_H
            mid = y + self.ROW_H / 2
            if kind == "label":
                d.text((x0 + 18, mid + 8), entry, font=F["small_b"], fill=MUTED, anchor="lm")
                continue
            selected = i == sel
            if selected:
                d.rounded_rectangle((x0, y + 3, x1, y + self.ROW_H - 3), radius=10, fill=ROW)
                d.rounded_rectangle((x0, y + 13, x0 + 4, y + self.ROW_H - 13), radius=2, fill=ACCENT)
            bx0, by0, bx1, by1 = x0 + 18, y + 6, x0 + 18 + 48, y + self.ROW_H - 6
            if kind == "add":
                d.rounded_rectangle((bx0, by0, bx1, by1), radius=8, outline=ACCENT, width=2)
                cxm, cym = (bx0 + bx1) / 2, (by0 + by1) / 2
                d.line((cxm - 8, cym, cxm + 8, cym), fill=ACCENT, width=3)
                d.line((cxm, cym - 8, cxm, cym + 8), fill=ACCENT, width=3)
                title, right, colour = "Add a camera…", "", MUTED
            else:
                k = cam_key(entry["addr"])
                th = cam.thumbs.get(k)
                if th:
                    pic = turn_picture(th[1], cam.turn_of(entry["addr"]))
                    s = min(48 / pic.width, 36 / pic.height)
                    pic = pic.resize((max(1, int(pic.width * s)), max(1, int(pic.height * s))))
                    d.rounded_rectangle((bx0, by0, bx1, by1), radius=6, fill=BG)
                    img.paste(pic, (int(bx0 + (48 - pic.width) / 2), int(by0 + (36 - pic.height) / 2)))
                else:
                    d.rounded_rectangle((bx0, by0, bx1, by1), radius=6, fill=BG if selected else ROW)
                    d.ellipse(((bx0 + bx1) / 2 - 9, (by0 + by1) / 2 - 9, (bx0 + bx1) / 2 + 9,
                               (by0 + by1) / 2 + 9), outline=MUTED, width=2)
                title = cam.name_of(entry["addr"]) if kind == "cam" else entry["name"]
                gone = k in cam.missing and k not in cam.thumbs
                right = "Can't reach" if gone else cam_host(entry["addr"])
                colour = WARN if gone else MUTED
            tx = bx1 + 14
            rw = d.textlength(right, font=F["small"]) if right else 0
            if right:
                d.text((x1 - 14, mid), right, font=F["small"], fill=colour, anchor="rm")
            font = F["row_b"] if selected else F["row"]
            d.text((tx, mid), self.fit(d, title, font, x1 - 14 - rw - 16 - tx), font=font,
                   fill=TEXT if selected else BODY, anchor="lm")
        if n == 1:                                    # nothing yet but the row to add one
            y = top_y + self.ROW_H + 18
            for line in ("A Pi running Pitato's camera server",
                         "(sudo bash setup.sh --camera on that Pi),", "or any MJPEG or JPEG camera link."):
                d.text((W / 2, y), line, font=F["small"], fill=MUTED, anchor="mm")
                y += 22
        kind, entry = rows[sel]
        if kind == "cam":
            remove = ("X", "Remove" if self.confirm[0] != "camdel:" + cam_key(entry["addr"]) else "Remove it")
            if cam.may_steer(entry["addr"]):          # (one that may turn: ◀▶ swaps left and right; lit: swapped)
                flip = cam.flipped(entry["addr"])
                hints = [("A", "Watch"), ("Y", "Rotate"),
                         ("◀▶", "Left/right swapped" if flip else "Swap left/right", flip), remove, ("B", "Home")]
            else:
                hints = [("A", "Watch"), ("Y", "Rotate"), remove, ("L R", "Tabs"), ("B", "Home")]
        else:
            hints = [("A", "Add"), ("L R", "Tabs"), ("B", "Home")]
        about = ""
        if entry:
            about = entry["addr"].split("://", 1)[-1]
            what = cam.kind_of(entry["addr"]) or entry.get("server", "")
            about += f" · {what}" if what else ""
        self.footer(d, hints, right=about)
        self.fb.show(img)
