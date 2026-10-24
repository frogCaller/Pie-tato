"""The Jellyfin tab: finding your server, signing in, your libraries, Continue watching and search. Its videos
play as Plex's do (screens/plex.py)."""
import hashlib
import io
import os
import threading
import time
import urllib.error

from ..theme import ACCENT, MUTED, ROW, TEXT
from ..config import CACHE_DIR
from ..util import item
from ..jellyfin import TICKS


JF_LIBRARY = {"movies": ("Movies", "movie"), "tvshows": ("TV shows", "show"), "boxsets": ("Collections", "SETS")}


def jf_seconds(ticks):
    try:
        return max(float(ticks or 0) / TICKS, 0.0)
    except (TypeError, ValueError):
        return 0.0


class JellyfinScreen:
    """The Jellyfin tab: finding your server, signing in, your libraries, Continue watching and search."""

    def jf_rows(self, raw, context=""):
        """Jellyfin's items as rows: films and episodes to play; shows, seasons and folders to open."""
        out = []
        for m in raw:
            if not (isinstance(m, dict) and m.get("Id")):
                continue
            t, iid, name = m.get("Type") or "", str(m["Id"]), str(m.get("Name") or "")
            ud = m.get("UserData") if isinstance(m.get("UserData"), dict) else {}
            tags = m.get("ImageTags") if isinstance(m.get("ImageTags"), dict) else {}
            if tags.get("Primary"):
                thumb = f"{iid}/{tags['Primary']}"
            elif m.get("SeriesId") and m.get("SeriesPrimaryImageTag"):    # (an episode with no picture: the show's)
                thumb = f"{m['SeriesId']}/{m['SeriesPrimaryImageTag']}"
            else:
                thumb = None
            row = {"thumb": thumb, "server": "jellyfin"}
            if t in ("Movie", "Episode", "Video", "MusicVideo"):
                sub, ptype = "", "clip"
                if t == "Movie":
                    sub, ptype = str(m.get("ProductionYear") or ""), "movie"
                elif t == "Episode":
                    ptype = "episode"
                    if context == "season":
                        name = f"{m['IndexNumber']}. {name}" if m.get("IndexNumber") is not None else name
                    else:
                        sub = name
                        name = (f"{m.get('SeriesName') or ''}  S{m.get('ParentIndexNumber', '?')}"
                                f" E{m.get('IndexNumber', '?')}")
                    row["series"] = m.get("SeriesId")
                out.append(dict(item("jf:" + iid, name, "jfvideo", iid, sub=sub), dur=jf_seconds(m.get("RunTimeTicks")),
                                off=jf_seconds(ud.get("PlaybackPositionTicks")), watched=bool(ud.get("Played")),
                                ptype=ptype, **row))
            elif t == "Series":
                n = m.get("RecursiveItemCount")
                out.append(dict(item("jfdir:" + iid, name, "jfdir", "series:" + iid, sub=f"{n} episodes" if n else ""),
                                ptype="show", unwatched=ud.get("UnplayedItemCount") or None, **row))
            elif t == "Season":
                n = m.get("ChildCount") or m.get("RecursiveItemCount")
                series = m.get("SeriesId") or m.get("ParentId") or ""
                out.append(dict(item("jfdir:" + iid, name, "jfdir", f"season:{series}:{iid}",
                                     sub=f"{n} episodes" if n else ""),
                                ptype="season", unwatched=ud.get("UnplayedItemCount") or None, **row))
            elif m.get("IsFolder"):                    # a folder, or a collection of films
                out.append(dict(item("jfdir:" + iid, name, "jfdir", "folder:" + iid), ptype="folder", **row))
        return out

    def jf_open(self, path, title):
        ji = self.tab_index("jellyfin")
        if self.jf_stack:
            self.jf_stack[-1]["sel"] = self.sels.get(ji, 0)
            self.jf_stack[-1]["top"] = self.tops.get(ji, 0)
        self.status[ji] = "loading"
        self.dirty = True
        threading.Thread(target=self.jf_fetch, args=(path, title), daemon=True).start()

    def jf_fetch(self, path, title):
        ji = self.tab_index("jellyfin")
        jf = self.jellyfin
        try:
            try:
                items = self.jf_list(path)
            except urllib.error.HTTPError:
                raise
            except OSError:                            # no answer: the server may have a new address
                if path != "root" or not jf.find_server(same=True):
                    raise
                items = self.jf_list(path)
            level = {"title": title, "path": path, "items": items, "sel": 0, "top": 0}
            if path == "root":
                self.jf_stack = [level]
            else:
                self.jf_stack.append(level)
            self.items[ji], self.sels[ji], self.tops[ji] = items, 0, 0
            if items or not path.startswith("search:"):
                self.status.pop(ji, None)
            else:
                self.status[ji] = "empty"
        except urllib.error.HTTPError as ex:
            if ex.code == 401:                         # signed out on the server (from its dashboard, say)
                self.toast("Jellyfin signed you out. Press A to sign in again", 5)
                jf.forget()
                self.jf_stack = []
                self.items[ji] = []
                self.status.pop(ji, None)
            else:
                self.jf_failed(ji)
        except Exception:
            self.jf_failed(ji)
        self.dirty = True
        self.start_jf_thumbs()

    def jf_failed(self, ji):
        self.status[ji] = "error"
        if self.jf_stack:
            self.toast("Couldn't reach your Jellyfin server")

    def jf_list(self, path):
        jf = self.jellyfin
        if path == "root":
            rows = [dict(item("jfsearch", "Search", "jfsearch", "search", sub="Movies and shows"),
                         thumb=None, ptype="search", icon="find")]
            cont = self.jf_continue()
            rows.append(dict(item("jfdeck", "Continue watching", "jfdir", "continue",
                                  sub=f"{len(cont)} to finish" if cont else "Nothing in progress"),
                             thumb=None, ptype="deck", icon="deck"))
            for v in jf.views():
                kind = v.get("CollectionType") or ""
                sub, icon = JF_LIBRARY.get(kind, ("Videos", "VID"))
                rows.append(dict(item("jflib:" + str(v["Id"]), str(v.get("Name") or sub), "jfdir",
                                      f"lib:{v['Id']}:{kind}", sub=sub), thumb=None, ptype="section", icon=icon))
            rows.append(item("act:jellyfin_signout", "Sign out of Jellyfin", "action", "jellyfin_signout"))
            return rows
        if path == "continue":
            return self.jf_continue()
        what, _, rest = path.partition(":")
        if what == "lib":
            lib, _, kind = rest.partition(":")
            return self.jf_rows(jf.library(lib, kind))
        if what == "series":
            seasons = jf.seasons(rest)
            if len(seasons) == 1 and seasons[0].get("Id"):      # one season: its episodes straight away
                return self.jf_rows(jf.episodes(rest, seasons[0]["Id"]), "season")
            return self.jf_rows(seasons)
        if what == "season":
            series, _, season = rest.partition(":")
            return self.jf_rows(jf.episodes(series, season), "season")
        if what == "folder":
            return self.jf_rows(jf.items(parentId=rest))
        if what == "search":
            return self.jf_rows(jf.search(rest))
        return []

    def jf_continue(self):
        """Films and episodes you haven't finished, then the next episodes of the shows you're watching."""
        raw, seen = [], set()
        for get in (self.jellyfin.resume, self.jellyfin.next_up):
            try:
                got = get()
            except urllib.error.HTTPError as ex:
                if ex.code == 401:
                    raise
                continue                               # (a server without one of them)
            for m in got:
                if isinstance(m, dict) and m.get("Id") not in seen:
                    seen.add(m.get("Id"))
                    raw.append(m)
        return self.jf_rows(raw)

    def jf_back(self):
        ji = self.tab_index("jellyfin")
        if len(self.jf_stack) > 1 and self.status.get(ji) != "loading":
            self.jf_stack.pop()
            lvl = self.jf_stack[-1]
            self.items[ji], self.sels[ji], self.tops[ji] = lvl["items"], lvl["sel"], lvl["top"]
            self.status.pop(ji, None)
            self.dirty = True
            return True
        return False

    # -- signing in ---------------------------------------------------------------------------------------------------
    def jf_sign_in(self):
        ji = self.tab_index("jellyfin")
        self.status[ji] = "finding"
        self.dirty = True
        threading.Thread(target=self.jf_login_loop, daemon=True).start()

    def jf_say(self, status):
        ji = self.tab_index("jellyfin")
        if status:
            self.status[ji] = status
        else:
            self.status.pop(ji, None)
        self.dirty = True

    def jf_login_loop(self):
        jf = self.jellyfin
        jf.load()                                      # (jellyfin.txt may be new)
        try:
            found = jf.find_server()
        except Exception:
            found = False
        if not found:
            return self.jf_say("noserver")
        if not jf.ready and jf.can_use_password():
            self.jf_say("signing")
            try:
                if not jf.sign_in_with_password():
                    return self.jf_say("badlogin")
            except urllib.error.HTTPError:
                return self.jf_say("badlogin")
            except Exception:
                return self.jf_say("offline")
        elif not jf.ready:
            try:
                if not jf.quick_on():
                    return self.jf_say("noquick")
                jf.start_quick()
            except Exception:
                return self.jf_say("offline")
            self.jf_say(None)
            while True:
                q = jf.quick
                if not q or time.monotonic() >= q["until"]:
                    break
                time.sleep(2)
                try:
                    if jf.check_quick():
                        break
                except urllib.error.HTTPError as ex:
                    if ex.code in (401, 404):          # the code's gone (too old, or Quick Connect turned off)
                        break
                except Exception:
                    pass
            if not jf.ready:
                jf.quick = None
                self.toast("That code expired. Press A for a new one")
                return
        self.jf_say(None)
        self.jf_open("root", "Jellyfin")

    # -- pictures ---------------------------------------------------------------------------------------------------
    def jf_thumb_file(self, key):
        return os.path.join(CACHE_DIR, "jellyfin", hashlib.md5(
            f"{self.jellyfin.cfg.get('server_id')}{key}".encode()).hexdigest() + ".jpg")

    def jf_thumb(self, it, size):
        key = f"jf:{it.get('thumb')}:{size}"
        im = self.thumbs.get(key)
        if im is not None:
            return im
        fn = self.jf_thumb_file(key)
        if os.path.exists(fn):
            from PIL import Image
            try:
                im = Image.open(fn)
                im.load()
                self.keep_thumb(key, im)
                return im
            except OSError:
                pass
        return None

    def start_jf_thumbs(self):
        if self.active and not (self.jfthumber and self.jfthumber.is_alive()):
            self.jfthumber = threading.Thread(target=self.jf_thumb_loop, daemon=True)
            self.jfthumber.start()

    def jf_thumb_loop(self):
        """Posters (and episodes' pictures) for the rows on screen, and the next page."""
        from PIL import Image, ImageOps
        os.makedirs(os.path.join(CACHE_DIR, "jellyfin"), exist_ok=True)
        failed = set()
        ji = self.tab_index("jellyfin")
        while self.active and self.tab == ji and self.jellyfin.ready:
            if self.proc_owns_screen():
                time.sleep(0.5)
                continue
            items = self.tab_items(ji)
            top, rows = self.tops.get(ji, 0), self.visible_rows()
            todo = None
            for it in items[top:top + rows * 2]:
                size = self.plex_size(it)
                if it.get("thumb") and (it["thumb"], size) not in failed and self.jf_thumb(it, size) is None:
                    todo = (it, size)
                    break
            if not todo:
                time.sleep(0.5)
                continue
            it, (w, h) = todo
            key = f"jf:{it['thumb']}:{(w, h)}"
            try:
                iid, tag = it["thumb"].split("/", 1)
                data = self.jellyfin.image(iid, tag, w * 2, h * 2)
                im = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (w, h), Image.BILINEAR)
                im.save(self.jf_thumb_file(key))
                self.keep_thumb(key, im)
                self.dirty = True
            except Exception:
                failed.add((it["thumb"], (w, h)))

    # -- the sign-in page ---------------------------------------------------------------------------------------------
    def render_jf_signin(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        mid = (self.HEADER + H - self.FOOTER) / 2
        st = self.status.get(self.tab)
        q = self.jellyfin.quick
        hints = [("A", "Sign in"), ("L R", "Tabs"), ("B", "Back")]
        if q:
            d.text((W / 2, mid - 84), "In Jellyfin on your phone or computer, open your profile, then",
                   font=F["small"], fill=MUTED, anchor="mm")
            d.text((W / 2, mid - 56), "Quick Connect", font=F["big"], fill=TEXT, anchor="mm")
            code = " ".join(q["code"])
            cw = d.textlength(code, font=F["code"]) + 56
            d.rounded_rectangle(((W - cw) / 2, mid - 30, (W + cw) / 2, mid + 46), radius=16, fill=ROW)
            d.text((W / 2, mid + 8), code, font=F["code"], fill=ACCENT, anchor="mm")
            mins = max(int((q["until"] - time.monotonic()) // 60), 0)
            d.text((W / 2, mid + 74), f"and type this code. Waiting…  (good for {mins} min)",
                   font=F["small"], fill=MUTED, anchor="mm")
            hints = [("L R", "Tabs"), ("B", "Back")]
        else:
            named = bool(self.jellyfin.manual.get("server"))
            big, small = {
                "finding": ("Looking for your Jellyfin server", "One moment"),
                "signing": ("Signing in", "One moment"),
                "noserver": ("No Jellyfin server found",
                             "Check the address in jellyfin.txt and that the server is on, then press A" if named else
                             "Is it on? Press A to look again, or put its address in jellyfin.txt"),
                "badlogin": ("Couldn't sign in", "Check the user and password in jellyfin.txt, then press A"),
                "noquick": ("Quick Connect is off on your server",
                            "Turn it on in Jellyfin's Dashboard, or put a user and password in jellyfin.txt"),
                "offline": ("Can't reach your Jellyfin server", "Check the WiFi, then press A to try again"),
            }.get(st, ("Watch your Jellyfin library", "Press A to find your server and sign in"))
            cx, cy = W / 2, mid - 62                   # a screen with a play sign
            d.rounded_rectangle((cx - 34, cy - 24, cx + 34, cy + 24), radius=9, outline=ACCENT, width=4)
            d.polygon([(cx - 8, cy - 12), (cx + 14, cy), (cx - 8, cy + 12)], fill=ACCENT)
            d.text((W / 2, mid + 2), big, font=F["big"], fill=TEXT, anchor="mm")
            for k, line in enumerate(self.wrap(d, small, F["small"], W - 80, 2)):
                d.text((W / 2, mid + 34 + k * 22), line, font=F["small"], fill=MUTED, anchor="mm")
            if st in ("finding", "signing"):
                hints = [("L R", "Tabs"), ("B", "Back")]
        self.footer(d, hints)
        self.fb.show(img)
