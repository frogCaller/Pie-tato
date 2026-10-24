"""The Plex tab: signing in, your library, Continue watching, the watchlist and live TV."""
import hashlib
import os
import threading
import time
import urllib.parse
import urllib.request
import uuid

from ..theme import ACCENT, LINE, MUTED, ROW, TEXT
from ..config import CACHE_DIR
from ..util import clock, item, UA
from ..plex import PLEX_CACHE


class PlexScreen:
    """The Plex tab: signing in, your library, Continue watching, the watchlist and live TV."""

    # -- Plex ------------------------------------------------------------------
    def plex_items(self, mc, context=""):
        out = []
        for d in mc.get("Directory", []):                  # library sections
            if d.get("type") in ("movie", "show") and d.get("key") is not None:
                out.append(dict(item("plexsec:" + str(d["key"]), d.get("title", ""), "plexdir",
                                     f"/library/sections/{d['key']}/all",
                                     sub="Movies" if d["type"] == "movie" else "TV shows"),
                                thumb=None, ptype="section", icon=d["type"]))
        for m in mc.get("Metadata", []):
            t, rk = m.get("type"), str(m.get("ratingKey", ""))
            thumb = m.get("thumb") or m.get("parentThumb") or m.get("grandparentThumb")
            if t in ("movie", "episode", "clip"):
                title, sub = m.get("title", ""), ""
                if t == "movie":
                    sub = str(m.get("year") or "")
                elif context == "season":
                    title = f"{m.get('index', '')}. {title}"
                else:
                    sub = title
                    title = (f"{m.get('grandparentTitle', '')}  S{m.get('parentIndex', '?')}"
                             f" E{m.get('index', '?')}")
                out.append(dict(item("plex:" + rk, title, "plexvideo", rk, sub=sub),
                                dur=(m.get("duration") or 0) / 1000,
                                off=(m.get("viewOffset") or 0) / 1000,
                                watched=(m.get("viewCount") or 0) > 0, thumb=thumb, ptype=t))
            elif t in ("show", "season"):
                n, seen = m.get("leafCount"), m.get("viewedLeafCount")
                out.append(dict(item("plexdir:" + rk, m.get("title", ""), "plexdir",
                                     m.get("key", ""), sub=f"{n} episodes" if n else ""),
                                thumb=thumb, ptype=t,
                                unwatched=(n - seen) if n is not None and seen is not None else None))
        return out

    def plex_open(self, path, title, context=""):
        pi = self.tab_index("plex")
        if self.plex_stack:
            self.plex_stack[-1]["sel"] = self.sels.get(pi, 0)
            self.plex_stack[-1]["top"] = self.tops.get(pi, 0)
        self.status[pi] = "loading"
        self.dirty = True
        threading.Thread(target=self.plex_fetch, args=(path, title, context), daemon=True).start()

    def plex_fetch(self, path, title, context):
        pi = self.tab_index("plex")
        try:
            if path == "root":
                items = [dict(item("plexsearch", "Search", "plexsearch", "search",
                                   sub="Channels, movies and shows"), thumb=None, ptype="search", icon="find")]
                cont = self.plex_continue()
                items.append(dict(item("plexdeck", "Continue watching", "plexdir", "continue",
                                       sub=f"{len(cont)} to finish" if cont else "Nothing in progress"),
                                  thumb=None, ptype="deck", icon="deck"))
                if self.plex.signed_in:
                    items.append(dict(item("plexwatch", "Watchlist", "plexdir", "watchlist",
                                           sub="Your Plex watchlist"),
                                      thumb=None, ptype="watchlist", icon="list"))
                items += self.plex_items(self.plex.get("/library/sections"))
                if self.plex.signed_in:
                    items.append(dict(item("plexlivetv", "Live TV", "plexdir", "livetv",
                                           sub="Free channels"), thumb=None, ptype="livetv", icon="live"))
                    items.append(dict(item("plexmoviech", "Free movie channels", "plexdir",
                                           "livetv:~movie", sub="Movies, live"),
                                      thumb=None, ptype="livetv", icon="live"))
                items.append(item("act:plex_signout", "Sign out of Plex", "action", "plex_signout"))
            elif path == "continue":
                items = self.plex_continue()
            elif path == "watchlist":
                items = self.plex_watchlist_items()
            elif path.startswith("livetv"):
                items = self.plex_live_items(path)
            elif path.startswith("search:") or path.startswith("livesearch:"):
                items = self.plex_search(path.split(":", 1)[1], library=path.startswith("search:"))
                if not items:
                    self.status[pi] = "empty"
            else:
                items = self.plex_items(self.plex.get(path), context)
            level = {"title": title, "path": path, "context": context,
                     "items": items, "sel": 0, "top": 0}
            if path == "root":
                self.plex_stack = [level]
            else:
                self.plex_stack.append(level)
            self.items[pi], self.sels[pi], self.tops[pi] = items, 0, 0
            if items or self.status.get(pi) != "empty":
                self.status.pop(pi, None)
        except Exception:
            self.status[pi] = "error"
            if self.plex_stack:
                self.toast("Couldn't reach your Plex server")
        self.dirty = True
        self.start_plex_thumbs()

    def plex_continue(self):
        """Movies you haven't finished and the next episodes, newest first."""
        for path in ("/hubs/continueWatching/items", "/library/onDeck"):
            try:
                return self.plex_items(self.plex.get(path))
            except Exception:
                continue
        return []

    def plex_watchlist_items(self):
        """Your Plex watchlist, each matched to the copy on your server when there is one."""
        out = []
        for w in self.plex.watchlist():
            guid, m = w.get("guid") or "", None
            if guid:
                try:
                    m = self.plex.find_on_server(guid)
                except Exception:
                    m = None
            got = self.plex_items({"Metadata": [m]}) if m else []
            if got:
                out.append(got[0])
                continue
            thumb = w.get("thumb") or ""
            out.append(dict(item("plexwant:" + (guid or w.get("title", "")), w.get("title", ""),
                                 "plexwant", "", sub=str(w.get("year") or "")),
                            thumb=thumb if thumb.startswith("http") else None, ptype="want"))
        return out

    def plex_live_items(self, path):
        when, chans = self.plex_live
        if not chans or time.time() - when > 6 * 3600:
            chans = self.plex.live_channels()
            self.plex_live = (time.time(), chans)
        if path == "livetv":                          # genres, biggest first after "All"
            counts = {}
            for c in chans:
                counts[c["genre"]] = counts.get(c["genre"], 0) + 1
            items = [dict(item("plexlivesearch", "Search channels", "plexsearch", "livesearch",
                               sub="By name"), thumb=None, ptype="search", icon="find"),
                     dict(item("plexlive:all", "All channels", "plexdir", "livetv:*",
                               sub=f"{len(chans)} channels"), thumb=None, ptype="genre", icon="live")]
            for g in sorted(counts, key=lambda g: (-counts[g], g.lower())):
                items.append(dict(item("plexlive:g:" + g, g, "plexdir", "livetv:" + g,
                                       sub=f"{counts[g]} channels"), thumb=None, ptype="genre",
                                  icon="live"))
            return items
        genre = path.split(":", 1)[1]

        def wanted(c):
            if genre.startswith("~"):                 # any genre containing the word
                return genre[1:] in c["genre"].lower()
            return genre == "*" or c["genre"] == genre
        return [dict(item("plexlive:" + c["key"], c["title"], "live", "plexlive:" + c["key"],
                          sub=c["genre"]), thumb=c["thumb"] or None, ptype="channel")
                for c in chans if wanted(c)]

    def plex_search(self, query, library=True):
        """Live TV channels whose name (or kind) has every word you typed, then, for a
        search from the top, your server's movies, shows and episodes."""
        words = query.lower().split()
        when, chans = self.plex_live
        out = []
        if self.plex.signed_in:
            try:
                if not chans or time.time() - when > 6 * 3600:
                    chans = self.plex.live_channels()
                    self.plex_live = (time.time(), chans)
            except Exception:
                chans = []
            hits = [c for c in chans if all(w in (c["title"] + " " + c["genre"]).lower() for w in words)]
            hits.sort(key=lambda c: (not c["title"].lower().startswith(words[0]) if words else 0,
                                     c["title"].lower()))
            out += [dict(item("plexlive:" + c["key"], c["title"], "live", "plexlive:" + c["key"],
                              sub=c["genre"]), thumb=c["thumb"] or None, ptype="channel") for c in hits[:60]]
        if library:
            try:
                mc = self.plex.get("/hubs/search?" + urllib.parse.urlencode({"query": query, "limit": 20}))
                found = []
                for hub in mc.get("Hub") or []:
                    if hub.get("type") in ("movie", "show", "episode"):
                        found += hub.get("Metadata") or []
                out += self.plex_items({"Metadata": found})
            except Exception:
                pass
        return out

    def plex_back(self):
        pi = self.tab_index("plex")
        if len(self.plex_stack) > 1 and self.status.get(pi) != "loading":
            self.plex_stack.pop()
            lvl = self.plex_stack[-1]
            self.items[pi], self.sels[pi], self.tops[pi] = lvl["items"], lvl["sel"], lvl["top"]
            self.dirty = True
            return True
        return False

    def plex_sign_in(self):
        pi = self.tab_index("plex")
        self.status[pi] = "code"
        self.dirty = True
        threading.Thread(target=self.plex_login_loop, daemon=True).start()

    def plex_login_loop(self):
        pi = self.tab_index("plex")
        if not self.plex.signed_in:
            try:
                self.plex.start_pin()
            except Exception:
                self.status[pi] = "offline"
                self.dirty = True
                return
            self.status.pop(pi, None)
            self.dirty = True
            while self.plex.pin and time.monotonic() < self.plex.pin["until"]:
                time.sleep(2)
                try:
                    if self.plex.check_pin():
                        break
                except Exception:
                    pass
            if not self.plex.signed_in:
                self.plex.pin = None
                self.toast("That code expired. Press A for a new one")
                return
        self.status[pi] = "finding"
        self.dirty = True
        try:
            found = self.plex.find_server()
        except Exception:
            found = False
        if not found:
            self.status[pi] = "noserver"
            self.dirty = True
            return
        self.status.pop(pi, None)
        self.plex_open("root", "Plex")

    @staticmethod
    def plex_size(it):
        return {"episode": (56, 32), "channel": (48, 32)}.get(it.get("ptype"), (30, 44))

    def plex_thumb(self, it, size):
        key = f"plex:{it.get('thumb')}:{size}"
        im = self.thumbs.get(key)
        if im is not None:
            return im
        fn = os.path.join(CACHE_DIR, "plex", hashlib.md5(
            f"{self.plex.cfg.get('server')}{key}".encode()).hexdigest() + ".jpg")
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

    def start_plex_thumbs(self):
        if self.active and not (self.plexthumber and self.plexthumber.is_alive()):
            self.plexthumber = threading.Thread(target=self.plex_thumb_loop, daemon=True)
            self.plexthumber.start()

    def plex_thumb_loop(self):
        """Fetch poster thumbnails for the rows on screen (and the next page)."""
        import io
        from PIL import Image, ImageOps
        os.makedirs(os.path.join(CACHE_DIR, "plex"), exist_ok=True)
        failed = set()
        pi = self.tab_index("plex")
        while self.active and self.tab == pi and self.plex.ready:
            if self.proc_owns_screen():
                time.sleep(0.5)
                continue
            items = self.tab_items(pi)
            top, rows = self.tops.get(pi, 0), self.visible_rows()
            todo = None
            for it in items[top:top + rows * 2]:
                size = self.plex_size(it)
                if it.get("thumb") and (it["thumb"], size) not in failed \
                        and self.plex_thumb(it, size) is None:
                    todo = (it, size)
                    break
            if not todo:
                time.sleep(0.5)
                continue
            it, (w, h) = todo
            key = f"plex:{it['thumb']}:{(w, h)}"
            try:
                if it["thumb"].startswith("http"):     # a channel logo: fetched as is, fitted whole
                    req = urllib.request.Request(it["thumb"], headers=UA)
                    with urllib.request.urlopen(req, timeout=10) as r:
                        logo = Image.open(io.BytesIO(r.read())).convert("RGBA")
                    logo = ImageOps.contain(logo, (w - 4, h - 4), Image.BILINEAR)
                    im = Image.new("RGB", (w, h), LINE)
                    im.paste(logo, ((w - logo.width) // 2, (h - logo.height) // 2), logo)
                else:
                    data = self.plex.call(self.plex.thumb_url(it["thumb"], w * 2, h * 2),
                                          token=self.plex.cfg["server_token"], raw=True)
                    im = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (w, h),
                                      Image.BILINEAR)
                im.save(os.path.join(CACHE_DIR, "plex", hashlib.md5(
                    f"{self.plex.cfg.get('server')}{key}".encode()).hexdigest() + ".jpg"))
                self.keep_thumb(key, im)
                self.dirty = True
            except Exception:
                failed.add((it["thumb"], (w, h)))

    def vod(self, it):
        """The server a video's from: Jellyfin's are played as Plex's are."""
        return self.jellyfin if (it or {}).get("server") == "jellyfin" else self.plex

    @staticmethod
    def vod_name(it):
        return "Jellyfin" if (it or {}).get("server") == "jellyfin" else "Plex"

    def play_plex(self, queue, i, start=None):
        it = queue[i]
        self.stop()
        self.queue, self.qi = queue, i
        if start is None:
            near_end = it["dur"] and it["off"] > it["dur"] - 30
            start = it["off"] if it["off"] > 10 and not near_end else 0
        if self.active:
            self.render_wait(it["title"], f"Resuming at {clock(start)}" if start
                             else f"Getting it ready on your {self.vod_name(it)} server", playing=True)
        self.plex_start(it, start)

    def plex_start(self, it, start):
        session = uuid.uuid4().hex
        url = self.vod(it).stream_url(it["src"], start, session)
        args = self.video_args() + PLEX_CACHE + ["-volume", str(self.volume)]
        self.kind, self.cur, self.meta, self.paused = "plex", it, {}, False
        self.plex_session, self.plex_base, self.plex_mode = session, start, None
        self.next_vsize = True
        self.plex_last, self.pos, self.retry = start, -1.0, None
        self.next_query = time.monotonic() + 3
        self.next_timeline = time.monotonic() + 5
        self.spawn(args, "ffmpeg://" + url)

    def plex_now(self):
        """Where you are in the Plex video, in seconds from its start."""
        if self.plex_mode is None or self.pos < 0:
            return self.plex_last
        return self.pos if self.plex_mode == "abs" else self.plex_base + self.pos

    def plex_seek(self, delta, absolute=None):
        """Plex seeks restart the stream, so quick presses are added up first."""
        cur = self.plex_pending if self.plex_pending is not None else self.plex_now()
        target = absolute if absolute is not None else cur + delta
        length = self.cur.get("dur") or 0
        target = max(0, min(target, length - 5) if length else target)
        self.plex_pending, self.plex_pending_t = target, time.monotonic() + 0.8
        self.osd(f"Go to {clock(target)}" + (f" of {clock(length)}" if length else ""), 1500)

    def plex_restart(self, target):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.kill()
        threading.Thread(target=self.vod(self.cur).stop_transcode, args=(self.plex_session,),
                         daemon=True).start()
        self.plex_start(self.cur, target)

    def plex_finish(self, it, pos, session, done):
        """Tell Plex (or Jellyfin) where you stopped, or that you finished, and end the conversion."""
        if not it:
            return
        it["off"] = 0 if done else pos
        it["watched"] = it.get("watched") or done
        server = self.vod(it)

        def report():
            server.timeline(it["src"], "stopped", pos, it.get("dur"), session=session)
            if done:
                server.scrobble(it["src"])
            server.stop_transcode(session)
        threading.Thread(target=report, daemon=True).start()

    def plex_art(self, img, d, x, mid, it, slot=0):
        """Poster (or episode still) at the start of a Plex (or Jellyfin) row."""
        F = self.fonts
        icon = it.get("icon")
        if icon:
            label = {"deck": "NEXT", "movie": "FILM", "show": "TV", "live": "LIVE", "find": "FIND",
                     "list": "LIST"}.get(icon, icon)
            d.rounded_rectangle((x, mid - 10, x + 40, mid + 10), radius=5, outline=ACCENT, width=1)
            d.text((x + 20, mid), label, font=F["badge"], fill=ACCENT, anchor="mm")
            return x + 52
        w, h = self.plex_size(it)
        y = int(mid - h / 2)
        thumb = self.jf_thumb if it.get("server") == "jellyfin" else self.plex_thumb
        t = thumb(it, (w, h)) if it.get("thumb") else None
        if t is not None:
            img.paste(t, (int(x), y))
        else:
            d.rounded_rectangle((x, y, x + w, y + h), radius=3, fill=LINE)
        return x + max(w, slot) + 12

    def render_plex_signin(self):
        F = self.fonts
        img, d = self.canvas()
        W, H = self.fb.w, self.fb.h
        self.header(img, d)
        mid = (self.HEADER + H - self.FOOTER) / 2
        st = self.status.get(self.tab)
        pin = self.plex.pin
        hints = [("A", "Sign in"), ("L R", "Tabs"), ("B", "Back")]
        if pin:
            d.text((W / 2, mid - 78), "On your phone or computer, go to",
                   font=F["small"], fill=MUTED, anchor="mm")
            d.text((W / 2, mid - 52), "plex.tv/link", font=F["big"], fill=TEXT, anchor="mm")
            code = "  ".join(pin["code"])
            cw = d.textlength(code, font=F["code"]) + 56
            d.rounded_rectangle(((W - cw) / 2, mid - 26, (W + cw) / 2, mid + 50), radius=16, fill=ROW)
            d.text((W / 2, mid + 12), code, font=F["code"], fill=ACCENT, anchor="mm")
            mins = max(int((pin["until"] - time.monotonic()) // 60), 0)
            d.text((W / 2, mid + 78), f"and type this code. Waiting…  (good for {mins} min)",
                   font=F["small"], fill=MUTED, anchor="mm")
            hints = [("L R", "Tabs"), ("B", "Back")]
        else:
            big, small = {
                "code": ("Getting a code", "One moment"),
                "finding": ("Signed in", "Looking for your Plex server"),
                "noserver": ("No Plex server found", "Make sure your server is on, then press A"),
                "offline": ("Can't reach plex.tv", "Check the WiFi, then press A to try again"),
            }.get(st, ("Watch your Plex library", "Press A to sign in with a code"))
            # a simple chevron, Plex-style
            cx, cy = W / 2, mid - 62
            d.polygon([(cx - 14, cy - 26), (cx + 2, cy - 26), (cx + 22, cy), (cx + 2, cy + 26),
                       (cx - 14, cy + 26), (cx + 6, cy)], fill=ACCENT)
            d.text((W / 2, mid + 2), big, font=F["big"], fill=TEXT, anchor="mm")
            d.text((W / 2, mid + 34), small, font=F["small"], fill=MUTED, anchor="mm")
            if st in ("code", "finding"):
                hints = [("L R", "Tabs"), ("B", "Back")]
        self.footer(d, hints)
        self.fb.show(img)
