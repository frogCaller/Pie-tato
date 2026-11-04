"""Songs' and videos' lengths read from their headers (lengths.py), against ffprobe's, for every kind it reads: MP3
(CBR with and without an Info header, VBR with Xing, VBR without, MPEG-2 and 2.5, layer II, a big ID3v2 tag with a
cover, an ID3v1 tag, a CRC), MP4/M4A/MOV (moov at either end), FLAC (with an ID3 tag before it), WAV (16 and 24-bit,
with a LIST chunk, one never finished), Ogg Vorbis and Opus. Broken and unknown files: None, and probe_length asks
ffprobe (or mplayer). How long each way takes."""
import os, shutil, subprocess, sys, time
from paths import SP, ROOT, TESTS  # noqa: E402  (this test's folder of work; the Pietato folder; tests)
D = SP + "/t_lengths"                         # (made once, kept)
sys.path.insert(0, ROOT)
import pitato.lengths as L

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg, flush=True)
    if not cond:
        fails.append(msg)


Q = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y"]
TONE = ["-f", "lavfi", "-i", "sine=frequency=330:duration={d}:sample_rate={r}"]
FILES = {   # name: (seconds, arguments after the input)
    "cbr128.mp3": (61.5, 44100, ["-c:a", "libmp3lame", "-b:a", "128k"]),
    "cbr_noxing.mp3": (33.0, 44100, ["-c:a", "libmp3lame", "-b:a", "192k", "-write_xing", "0"]),
    "vbr.mp3": (47.3, 44100, ["-c:a", "libmp3lame", "-q:a", "4"]),
    "vbr_noxing.mp3": (20.0, 44100, ["-c:a", "libmp3lame", "-q:a", "2", "-write_xing", "0"]),
    "mono22k.mp3": (12.2, 22050, ["-c:a", "libmp3lame", "-b:a", "48k", "-ac", "1"]),
    "eight_k.mp3": (9.0, 8000, ["-c:a", "libmp3lame", "-b:a", "16k", "-ac", "1"]),
    "layer2.mp3": (15.0, 48000, ["-c:a", "mp2", "-b:a", "192k", "-f", "mp2"]),
    "id3v1.mp3": (8.0, 44100, ["-c:a", "libmp3lame", "-b:a", "128k", "-write_id3v1", "1", "-metadata", "title=Song"]),
    "aac.m4a": (30.4, 44100, ["-c:a", "aac", "-b:a", "96k"]),
    "aac_fast.m4a": (30.4, 44100, ["-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]),
    "song.flac": (25.7, 44100, ["-c:a", "flac"]),
    "hi.flac": (5.25, 96000, ["-c:a", "flac", "-sample_fmt", "s32"]),
    "song.wav": (14.5, 44100, ["-c:a", "pcm_s16le", "-metadata", "title=Song"]),
    "deep.wav": (6.0, 48000, ["-c:a", "pcm_s24le", "-ac", "1"]),
    "song.ogg": (41.2, 44100, ["-c:a", "libvorbis", "-q:a", "3"]),
    "voice.opus": (22.6, 48000, ["-c:a", "libopus", "-b:a", "48k"]),
    "talk.oga": (10.0, 22050, ["-c:a", "libvorbis"]),
}


def make():
    if os.path.isdir(D + "/done"):
        return
    shutil.rmtree(D, ignore_errors=True)
    os.makedirs(D)
    for name, (secs, rate, args) in FILES.items():
        subprocess.run(Q + [a.format(d=secs, r=rate) for a in TONE] + args + [f"{D}/{name}"], check=True)
    # a big cover picture in the ID3 tag
    subprocess.run(Q + ["-f", "lavfi", "-i", "testsrc=size=1000x1000:duration=1", "-frames:v", "1", "-q:v", "2",
                        D + "/cover.jpg"], check=True)
    subprocess.run(Q + ["-i", D + "/cbr128.mp3", "-i", D + "/cover.jpg", "-map", "0", "-map", "1", "-c", "copy",
                        "-id3v2_version", "3", D + "/cover.mp3"], check=True)
    # videos: MP4 (moov at the end and at the start), MOV, and kinds read by ffprobe
    vid = ["-f", "lavfi", "-i", "testsrc2=size=320x240:rate=25:duration=12.4", "-f", "lavfi", "-i",
           "sine=duration=12.4"]
    subprocess.run(Q + vid + ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", D + "/clip.mp4"], check=True)
    subprocess.run(Q + vid + ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-movflags", "+faststart",
                              D + "/clip_fast.m4v"], check=True)
    subprocess.run(Q + vid + ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", D + "/clip.mov"], check=True)
    subprocess.run(Q + vid + ["-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", D + "/clip.mkv"], check=True)
    subprocess.run(Q + vid + ["-c:v", "mpeg4", "-c:a", "libmp3lame", D + "/clip.avi"], check=True)
    subprocess.run(Q + ["-f", "lavfi", "-i", "sine=duration=7"] + ["-c:a", "wmav2", D + "/tune.wma"], check=True)
    os.makedirs(D + "/done")


make()
for name, (secs, rate, args) in FILES.items():
    pass

# an ID3v2 tag in front of a FLAC; a WAV that never finished (its data chunk says it's bigger than it is); a MP3 with a
# CRC; broken and pretend files
W = SP + "/t_lengths_odd"
shutil.rmtree(W, ignore_errors=True)
os.makedirs(W)
tag = b"ID3\x03\x00\x00" + bytes([0, 0, 0x08, 0x00]) + bytes(0x400)
open(W + "/tagged.flac", "wb").write(tag + open(D + "/song.flac", "rb").read())
wav = bytearray(open(D + "/song.wav", "rb").read())
cut = len(wav) * 2 // 3
open(W + "/unfinished.wav", "wb").write(wav[:cut])
subprocess.run(Q + ["-f", "lavfi", "-i", "sine=duration=6", "-c:a", "mp2", "-b:a", "128k", "-f", "mp2",
                    W + "/crc.mp3"], check=True)
open(W + "/noise.mp3", "wb").write(os.urandom(50_000))
open(W + "/empty.mp3", "wb").close()
open(W + "/text.mp4", "w").write("not a video\n" * 100)
open(W + "/half.m4a", "wb").write(open(D + "/aac.m4a", "rb").read()[:5000])
open(W + "/fake.ogg", "wb").write(b"OggS" + os.urandom(3000))
open(W + "/fake.flac", "wb").write(b"fLaC" + os.urandom(100))


def ffprobe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                          path], capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return None


# ---- the kinds it reads: as long as ffprobe says --------------------------------------------------------------------
for name in sorted(list(FILES) + ["cover.mp3", "clip.mp4", "clip_fast.m4v", "clip.mov"]):
    p = D + "/" + name
    q, f = L.quick_length(p), ffprobe(p)
    want = FILES.get(name, (61.5 if name == "cover.mp3" else 12.4,))[0]
    if name == "vbr_noxing.mp3":                  # (VBR without a header to say how many frames: they're counted.
        check(q is not None and abs(q - want) < 0.1, f"{name}: frames counted, {q} (ffprobe guesses {f}, made {want})")
        continue                                  # mplayer counts them too)
    close = q is not None and f is not None and abs(q - f) < 0.15
    check(close and abs(q - want) < 0.15, f"{name}: {q if q is None else round(q, 3)} s (ffprobe {f}, made {want})")
check(os.path.getsize(D + "/cover.mp3") > os.path.getsize(D + "/cbr128.mp3") + 50_000, "...the cover's in its ID3 tag")
p = W + "/tagged.flac"
check(abs((L.quick_length(p) or 0) - 25.7) < 0.05, f"an ID3 tag before a FLAC: {L.quick_length(p)}")
p = W + "/unfinished.wav"
q, f = L.quick_length(p), ffprobe(p)
check(q is not None and abs(q - 14.5 * 2 / 3) < 0.2, f"a WAV that never finished: {q} (ffprobe {f})")
q, f = L.quick_length(W + "/crc.mp3"), ffprobe(W + "/crc.mp3")
check(q is not None and abs(q - f) < 0.15, f"layer II: {q} (ffprobe {f})")
for name in ("a.mp3", "upl2/Autumn Leaves.mp3", "upl3/song.mp3"):
    p = SP + "/" + name
    if os.path.exists(p):
        q, f = L.quick_length(p), ffprobe(p)
        check((q is None) if f is None else (q is not None and abs(q - f) < 0.5),
              f"{'a real one' if f else 'not really an MP3'}, {name}: {q} (ffprobe {f})")

# ---- not read from the header: None, and probe_length asks ffprobe -------------------------------------------------
for name in ("clip.mkv", "clip.avi", "tune.wma"):
    p = D + "/" + name
    check(L.quick_length(p) is None, f"{name}: not from its header")
    n, f = L.probe_length(p), ffprobe(p)
    check(abs(n - f) < 0.01, f"...ffprobe tells: {n}")
for name in ("noise.mp3", "empty.mp3", "text.mp4", "half.m4a", "fake.ogg", "fake.flac"):
    check(L.quick_length(W + "/" + name) is None, f"{name}: None")
check(L.probe_length(W + "/empty.mp3") == 0.0 and L.probe_length(W + "/text.mp4") == 0.0, "...and 0.0 in the end")
check(L.probe_length(W + "/gone.mp3") == 0.0, "a file that's gone: 0.0")
real_which = shutil.which
L.shutil.which = lambda n: None
n = L.probe_length(D + "/clip.mkv")
L.shutil.which = real_which
check(abs(n - 12.4) < 0.2, f"no ffprobe: mplayer tells ({n})")

# ---- how long it takes --------------------------------------------------------------------------------------------
songs = [D + "/" + n for n in FILES]
t0 = time.perf_counter()
for _ in range(20):
    for p in songs:
        L.quick_length(p)
quick = (time.perf_counter() - t0) / (20 * len(songs)) * 1000
t0 = time.perf_counter()
for p in songs[:6]:
    subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", p], capture_output=True)
slow = (time.perf_counter() - t0) / 6 * 1000
print(f"from the header: {quick:.2f} ms a file; ffprobe: {slow:.0f} ms a file")
check(quick * 20 < slow, "far quicker than ffprobe")
print("ALL OK" if not fails else f"FAILED: {len(fails)}")
