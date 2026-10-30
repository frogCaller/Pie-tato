"use strict";
// A game from the Pi, played here in EmulatorJS (GPL-3.0, emulatorjs.org): what to play is in this page's address (the
// Screen view puts it there, where the Pi's screen was). Its in-game save comes from the Pi as it starts, and goes
// back to the Pi as the game makes it, and when it's closed, so you can carry on there.
(() => {
  const q = new URLSearchParams(location.search);
  const CORES = {                                 // the systems it plays, and the core each needs
    fceumm: "fceumm", snes9x: "snes9x", gambatte: "gambatte", mgba: "mgba", segaMD: "genesis_plus_gx",
    segaGG: "genesis_plus_gx", smsplus: "smsplus", mupen64plus_next: "mupen64plus_next",
    pcsx_rearmed: "pcsx_rearmed", melonds: "melonds",
  };
  const core = q.get("core") || "", rom = q.get("rom") || "", bios = q.get("bios") || "";
  const save = /^Saves\/[^/]+\.srm$/.test(q.get("save") || "") ? q.get("save") : "";
  const color = /^#[0-9a-f]{6}$/i.test(q.get("color") || "") ? q.get("color") : "#60aae4";
  const home = (p) => "/api/home/" + p.split("/").map(encodeURIComponent).join("/");
  const note = document.getElementById("note");
  let started = false, sent = null, turn = Promise.resolve();

  function tell(what) {                           // (to the Screen view)
    if (parent !== window) parent.postMessage(Object.assign({ pietato: "game" }, what), location.origin);
  }
  function say(text, bad) {
    note.textContent = text;
    note.hidden = false;
    if (bad) tell({ error: text });
  }
  const same = (a, b) => !!a && !!b && a.length === b.length && a.every((v, i) => v === b[i]);
  const manager = () => window.EJS_emulator && window.EJS_emulator.gameManager;

  async function fromPi() {                       // the save the Pi has, into the game as it starts
    const gm = manager();
    if (!gm || !save) return;
    try {
      const r = await fetch("/api/file?folder=games&download=1&path=" + encodeURIComponent(save), { cache: "no-store" });
      if (!r.ok) return;                          // (none yet)
      const data = new Uint8Array(await r.arrayBuffer());
      if (!data.length) return;
      const path = gm.getSaveFilePath();
      let at = "";
      for (const part of path.split("/").slice(0, -1)) {
        if (!part) continue;
        at += "/" + part;
        if (!gm.FS.analyzePath(at).exists) gm.FS.mkdir(at);
      }
      if (gm.FS.analyzePath(path).exists) gm.FS.unlink(path);
      gm.FS.writeFile(path, data);
      gm.loadSaveFiles();
      sent = data;
    } catch (e) {
      console.warn("The save from the Pi didn't load", e);
    }
  }
  function toPi(data) {                           // the save back to the Pi, if it's changed (one at a time)
    turn = turn.then(async () => {
      if (!save || !data || !data.length || same(data, sent)) return true;
      try {
        const r = await fetch("/api/upload?folder=games&exists=replace&path=" + encodeURIComponent(save),
          { method: "PUT", body: data, headers: { "Content-Type": "application/octet-stream" } });
        if (r.ok) sent = data.slice();
        return r.ok;
      } catch (e) {
        return false;
      }
    });
    return turn;
  }
  function saveNow() {
    const gm = manager();
    if (!started || !gm) return Promise.resolve(true);
    try { return toPi(gm.getSaveFile()); } catch (e) { return Promise.resolve(false); }
  }

  window.addEventListener("message", async (e) => {
    if (e.source !== parent || e.origin !== location.origin || !e.data || e.data.pietato !== "close") return;
    const saved = await saveNow();
    tell({ closed: true, saved });
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden) saveNow(); });   // (a phone put away)

  async function start() {
    const pkg = CORES[core];
    if (!pkg || !rom) return say("That game can't play here", true);
    say("Getting the emulator ready…");
    let r = null;
    try { r = await fetch("/api/ejs?core=" + encodeURIComponent(pkg), { method: "POST", headers: { "X-Pitato-Page": "1" } }); }
    catch (e) { return say("The Pi isn't answering", true); }
    if (!r.ok) {
      let why = "The Pi couldn't get the emulator";
      try { why = (await r.json()).error || why; } catch (e) {}
      return say(why, true);
    }
    note.hidden = true;
    const touch = matchMedia("(pointer: coarse)").matches;   // (a phone: its Start, tapped, brings the game's buttons
    Object.assign(window, {                                   // on the screen, and lets its sound play)
      EJS_player: "#game", EJS_core: core, EJS_gameUrl: home(rom), EJS_gameName: q.get("name") || "Game",
      EJS_pathtodata: "/ejs/data/", EJS_startOnLoaded: !touch, EJS_startButtonName: "Start",
      EJS_language: "en-US", EJS_disableAutoLang: false,
      EJS_color: color, EJS_backgroundColor: "#000000", EJS_biosUrl: bios ? home(bios) : "",
      EJS_defaultOptions: { "save-save-interval": "30",      // (the game's save, every half a minute: to the Pi too)
        "virtual-gamepad": touch ? "enabled" : "disabled" }, // (a tablet's buttons on the screen too, as a phone's)
      EJS_ready: () => window.EJS_emulator.on("saveSaveFiles", (data) => toPi(data)),
      EJS_onGameStart: async () => { await fromPi(); started = true; tell({ started: true }); },
    });
    const s = document.createElement("script");
    s.src = "/ejs/data/loader.js";
    s.onerror = () => say("The emulator didn't load", true);
    document.body.append(s);
  }
  start();
})();
