"""Apps' Fortune Cookie: a fortune on the page, a fortune cookie over it and lucky numbers under it, in the colours,
font and effect you pick (as Notes has them). A cracks a new cookie open: a new fortune (not one you've had lately).
The d-pad picks its colours (up and down the words', left and right the background's), L and R its font, Y an effect
(a glow, a rainbow, a shadow), X reads it out loud in your Bot's voice. START has them all, and how big the letters
are; SELECT is the whole screen, B goes back. (screens/fortune.py: its buttons.)"""
import math
import time

from .fine import detail
from .notes import Notes, NOTE_FONTS, NOTE_SIZES
from .theme import co_mix, typeface

FORTUNE_SIZE = 30            # px: Clean's letters, Normal (the others as big to look at: theme.py)
FORTUNE_CRACK = 0.8          # seconds a cookie takes to crack open (its fortune coming in as it does)
FORTUNE_FPS = 25             # ...its frames a second meanwhile
FORTUNE_STILL = 30.0         # seconds between its frames otherwise (nothing on it changes by itself)
FORTUNE_COOKIE = 104         # px across, the cookie
FORTUNE_NUMBERS = 6          # lucky numbers, from 1 to 49
COOKIE = ((228, 174, 98), (186, 126, 58), (248, 210, 146))   # its colour, its shade, its light
SLIP = ((250, 247, 238), (214, 206, 190))                    # the paper in it, and its edge
FORTUNES = (
    "A small step today saves a long walk tomorrow.",
    "The answer you're looking for is closer than you think.",
    "Someone is glad you exist today.",
    "Your next idea will be your best one yet.",
    "A good laugh is coming your way.",
    "Today is a fine day to finish something you started.",
    "The best view comes after the hardest climb.",
    "You will soon find something you thought was lost.",
    "A pleasant surprise is waiting around the corner.",
    "Patience now will pay you back twice.",
    "You already know the right thing to do.",
    "Good things come to those who press A.",
    "Your kindness will come back to you in an unexpected way.",
    "An old friend is thinking of you.",
    "Trust the plan, but keep a snack nearby.",
    "A new hobby will bring you joy.",
    "The stars say: take a break and stretch.",
    "You will win the next game you play. Probably.",
    "Something you build this week will make someone smile.",
    "Today, the little things will go your way.",
    "Your curiosity will lead you somewhere wonderful.",
    "A quiet morning will bring a clever idea.",
    "You are braver than you feel.",
    "Help will arrive just when you need it.",
    "Say yes to the next good invitation.",
    "A walk outside will clear your mind.",
    "You will learn something new before the day is done.",
    "The best is yet to come.",
    "Fortune favors the well rested.",
    "A small gift will mean a lot to someone.",
    "Your hard work is about to pay off.",
    "You will hear good news from far away.",
    "Don't forget to drink some water.",
    "Your smile is your best accessory today.",
    "Someone will ask for your advice. Give it kindly.",
    "The cookie is crumbly, but your future is bright.",
    "You will discover a new favorite song.",
    "A change of scenery will do you good.",
    "Today is a good day for a fresh start.",
    "Every expert was once a beginner.",
    "You will find the perfect word at the perfect time.",
    "Your plants are proud of you.",
    "A tidy desk will lead to a clear mind.",
    "Good company is on its way.",
    "You will make a wise choice today.",
    "The thing you're worried about will turn out fine.",
    "Adventure is calling. Maybe answer it.",
    "A cup of something warm will make everything better.",
    "Your lucky color today is whatever you're wearing.",
    "Someone admires your work more than you know.",
    "Laughter is the best upgrade.",
    "A little rest goes a long way.",
    "You will soon solve a puzzle that's been bugging you.",
    "Today you'll be in the right place at the right time.",
    "A good book will find you.",
    "Fix one small thing today. It will feel great.",
    "You will receive a compliment you didn't expect.",
    "Be the reason someone smiles today.",
    "Your next game will be a high score.",
    "The WiFi will be strong with you today.",
    "You will remember where you put it.",
    "An unexpected message will brighten your day.",
    "Courage is just fear that said hello anyway.",
    "The road ahead is smoother than it looks.",
    "You have a knack for making things work.",
    "Something delicious is in your near future.",
    "Today, trust your first idea.",
    "You will soon be thanked for something you forgot you did.",
    "A happy accident will teach you something.",
    "Let the music play a little louder today.",
    "You will make a new friend in an unlikely place.",
    "Keep going. You're closer than you think.",
    "The sun will shine on your plans.",
    "A simple idea will solve a tricky problem.",
    "Your future self says thanks.",
    "It's a good day to try the thing you've been putting off.",
    "Be gentle with yourself today.",
    "You will see something that makes you laugh out loud.",
    "The best ideas arrive in the shower.",
    "Your hands will make something worth keeping.",
    "Someone nearby could use a kind word.",
    "A spare moment will turn into a great one.",
    "Luck is on your side, but so is hard work.",
    "You will find a coin, a clue, or a cookie.",
    "Small steps still move you forward.",
    "A good night's sleep will change everything.",
    "Your project will come together sooner than you expect.",
    "Share your snack. Good luck follows.",
    "A new door will open. Walk through it.",
    "You will hear a song that takes you back.",
    "Today's mistake is tomorrow's story.",
    "You are someone's favorite person.",
    "A question you ask will change your mind.",
    "You will finish what you start this week.",
    "Something old will feel new again.",
    "Don't wait for the perfect moment. Take this one.",
    "Kindness costs nothing and pays forever.",
    "You will be surprised by how much you know.",
    "A short break will lead to a big breakthrough.",
    "Look up. Something beautiful is happening.",
    "Your next adventure starts with a single click.",
    "You will win an argument by listening.",
    "Today is a good day to call someone you miss.",
    "The cookie says: you've got this.",
    "A clever shortcut is about to reveal itself.",
    "Good news travels fast. Expect some soon.",
    "Your patience will be rewarded with pizza.",
    "You will soon be in the mood to dance.",
    "Bright ideas come in small packages.",
    "Something you planted will begin to grow.",
    "An open mind will find an open door.",
    "The best gift you can give today is your time.",
    "You will soon have a reason to celebrate.",
    "A friendly face will make your day.",
    "Look in the last place you'd look first.",
    "Today, every button you press will do something good.",
    "Keep it simple. It will work.",
    "Your energy will lift the people around you.",
    "A rainy day will bring a cozy surprise.",
    "The little Pi believes in you.",
)


def cookie_picture(size, t, s=1):
    """The fortune cookie, size px across (s: how finely the screen's drawn), t of the way cracked open (0: whole, its
    paper's corner showing at its fold; 1: its halves apart and turned out, the paper out between them): an RGBA
    picture, the cookie in its middle."""
    from PIL import Image, ImageDraw
    k = 4                                      # (drawn bigger, then shrunk: smooth edges)
    size = size * s
    W, H = int(size * 2.3), int(size * 0.95)
    img = Image.new("RGBA", (W * k, H * k), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rx, ry = size * k / 2, size * k * 0.36     # (the whole cookie: this wide and tall, from its middle)
    cx, cy = W * k / 2, H * k * 0.5
    t = max(0.0, min(1.0, t))
    ease = 1 - (1 - t) ** 3                    # (quick at first, settling)
    out = ease * size * k * 0.36               # how far each half's moved out
    tilt = math.radians(ease * 28)             # ...and turned, each its own way
    if t > 0.1:                                # the paper, coming out between them
        f = (t - 0.1) / 0.9
        pw, ph = size * k * (0.3 + 1.0 * f), size * k * 0.17
        y0 = cy + ry * 0.05
        d.rounded_rectangle((cx - pw / 2, y0 - ph / 2, cx + pw / 2, y0 + ph / 2), radius=ph * 0.2, fill=SLIP[0],
                            outline=SLIP[1], width=k)
        for i in range(3):                     # (its print, too small to read from here)
            x = cx - pw * 0.32 + i * pw * 0.24
            d.line((x, y0, x + pw * 0.16, y0), fill=SLIP[1], width=max(1, int(k * 1.6 * s)))
    for side in (-1, 1):
        def place(x, y):                       # (turned about the fold's foot, then moved out)
            px, py = cx, cy + ry * 0.55
            dx, dy = x - px, y - py
            a = side * tilt
            return (px + dx * math.cos(a) - dy * math.sin(a) + side * out,
                    py + dx * math.sin(a) + dy * math.cos(a))
        top = [place(cx + side * rx * math.sin(math.radians(a)), cy - ry * 0.95 * math.cos(math.radians(a)))
               for a in range(0, 121, 5)]     # its back, round over the top and down its side
        foot = [place(cx + side * rx * (0.86 - 0.8 * f), cy + ry * (0.48 + 0.42 * math.sin(math.pi * f)))
                for f in (i / 12 for i in range(13))]   # its foot, curling in under to the fold
        fold = [place(cx + side * rx * 0.05, cy + ry * 0.2), place(cx + side * rx * 0.02, cy - ry * 0.5)]
        d.polygon(top + foot + fold, fill=COOKIE[0])
        crease = [place(cx + side * rx * (0.12 + 0.4 * f), cy - ry * (0.55 - 1.0 * f) - ry * 0.25 * math.sin(
            math.pi * f)) for f in (i / 10 for i in range(11))]
        d.line(crease, fill=COOKIE[1], width=max(1, int(k * 2.4 * s)), joint="curve")
        light = [place(cx + side * rx * 0.78 * math.sin(math.radians(a)), cy - ry * 0.72 * math.cos(math.radians(a)))
                 for a in range(28, 84, 4)]
        d.line(light, fill=COOKIE[2], width=max(1, int(k * 2.6 * s)), joint="curve")
    if t <= 0.1:                               # whole: the paper's corner, peeking out of its fold
        pw, ph = size * k * 0.22, size * k * 0.11
        y0 = cy + ry * 0.62
        d.rounded_rectangle((cx - pw / 2, y0, cx + pw / 2, y0 + ph), radius=ph * 0.2, fill=SLIP[0],
                            outline=SLIP[1], width=k)
    return img.reduce(k)


class Fortune(Notes):
    """A fortune, on the page itself: a fortune cookie at the top (cracking open as a new one comes), the fortune in
    the middle in its colours, font and effect, and its lucky numbers under it."""
    key = "fortune"
    blurb = "A new fortune with A. The d-pad picks its colours, L and R its font, and Y an effect."

    def __init__(self, w, h, rng=None, values=None):
        super().__init__(w, h, rng, values)
        self.deck = []                  # fortunes still to come (all of them, in no order, then again)
        self.numbers = ()
        self.cracked = 0.0              # when the cookie was cracked open (time.time())
        self.pictures = {}              # the cookie, as it cracks: (size, s, step) -> it
        self.new(at=0.0)                # (the first: already open)

    def new(self, at=None):
        """A new fortune, its cookie cracking open now (at: when it was, time.time()): one you haven't had lately (all
        of them come before any comes again)."""
        if not self.deck:
            self.deck = list(range(len(FORTUNES)))
            self.rng.shuffle(self.deck)
            if self.text in FORTUNES and len(self.deck) > 1 and FORTUNES[self.deck[-1]] == self.text:
                self.deck.insert(0, self.deck.pop())   # (not the one just had, straight away again)
        self.text = FORTUNES[self.deck.pop()]
        self.numbers = tuple(sorted(self.rng.sample(range(1, 50), FORTUNE_NUMBERS)))
        self.cracked = time.time() if at is None else at

    def said(self):
        """What X reads out loud: the fortune, and its lucky numbers."""
        nums = [str(n) for n in self.numbers]
        return f"{self.text} Your lucky numbers are {', '.join(nums[:-1])} and {nums[-1]}."

    def cracking(self, wall=None):
        """How far its cookie's cracked open (1: open)."""
        wall = time.time() if wall is None else wall
        return max(0.0, min(1.0, (wall - self.cracked) / FORTUNE_CRACK))

    def frame_in(self, wall):
        """Seconds until its picture changes: often while its cookie cracks open, else now and then."""
        return 1.0 / FORTUNE_FPS if self.cracking(wall) < 1.0 else FORTUNE_STILL

    def hints(self):
        """Its buttons, along the bottom (on a screen wider than the GPi Case's, Y's, SELECT's and START's too)."""
        out = [("A", "New one"), ("▲▼", "Colour"), ("◀▶", "Background"), ("L R", "Font"),
               ("X", "Stop" if self.reading else "Read it")]
        return out + [("Y", "Effect"), ("SELECT", "Full screen"), ("START", "More")] if self.w >= 800 else out

    def font_size(self, shrink=1.0):
        """(its font's file, how big its letters are set, px): Font and Size's, smaller by shrink (a long fortune in big
        letters, to fit); a pixel font in steps of 4, and no smaller than 12."""
        name = self.values.get("font")
        path, k = typeface(name if name in NOTE_FONTS else "Clean")
        size = FORTUNE_SIZE * k * NOTE_SIZES.get(self.values.get("size"), 1.0) * shrink
        if name == "Pixel":
            return path, max(12, int(round(size / 4)) * 4)
        return path, max(10, int(round(size)))

    def font(self, s=1, shrink=1.0):
        path, size = self.font_size(shrink)
        key = (path, size * s)
        if key not in self.fonts:
            from PIL import ImageFont
            try:
                basic = ImageFont.Layout.BASIC if hasattr(ImageFont, "Layout") else ImageFont.LAYOUT_BASIC
                self.fonts[key] = ImageFont.truetype(path, size * s, layout_engine=basic)   # (quicker on a Pi)
            except OSError:
                self.fonts[key] = ImageFont.load_default()
        return self.fonts[key]

    def layout(self, H, s):
        """(the cookie's middle, the words' room: its top and bottom, the lucky numbers' baseline), down the page."""
        pad = 22 * s
        cookie = pad + FORTUNE_COOKIE * 0.42 * s
        numbers = H - pad
        return cookie, (cookie + FORTUNE_COOKIE * 0.52 * s, numbers - 30 * s), numbers

    def picture(self, W, H, s):
        """Its words, as a picture (W x H, see-through where there are none): the fortune in the middle of its room, its
        lines each in the middle; its lucky numbers under it. Made again only when something about them changes."""
        from .notes import wrap
        key = (self.text, self.numbers, self.values.get("ink"), self.values.get("paper"), self.values.get("font"),
               self.values.get("size"), self.values.get("effect"), W, H, s)
        if self.drawn[0] == key:
            return self.drawn[1]
        from PIL import Image, ImageDraw, ImageFilter
        ink, paper = self.ink(), self.backdrop
        pad = 30 * s
        _, (top, bottom), base = self.layout(H, s)
        for shrink in (1.0, 0.85, 0.72, 0.6, 0.5):     # (the biggest its lines fit)
            font = self.font(s, shrink)
            asc, desc = font.getmetrics()
            lh = int(max((asc + desc) * 1.12, font.size * 1.3))
            lines = [line.strip() for line, _ in wrap(self.text, font, W - 2 * pad)]
            if len(lines) * lh <= bottom - top:
                break
        mask = Image.new("L", (W, H), 0)
        md = ImageDraw.Draw(mask)
        y = top + max(0, (bottom - top - len(lines) * lh) // 2)
        for line in lines:
            md.text((W / 2, y), line, font=font, fill=255, anchor="ma")
            y += lh
        out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        effect = self.values.get("effect")
        if effect == "Glow":                           # a soft light round the letters, in their colour
            glow = mask.filter(ImageFilter.GaussianBlur(7 * s)).point(lambda v: min(255, v * 2))
            out.paste(Image.new("RGBA", (W, H), ink + (255,)), (0, 0), glow)
        elif effect == "Shadow":                       # a shadow behind them, down and to the right
            shade = co_mix(paper, (0, 0, 0), 0.65) if sum(paper) > 120 else co_mix(ink, paper, 0.75)
            out.paste(Image.new("RGBA", (W, H), shade + (255,)), (3 * s, 3 * s), mask)
        fill = self.rainbow(W, H) if effect == "Rainbow" else Image.new("RGBA", (W, H), ink + (255,))
        out.paste(fill, (0, 0), mask)
        nums = "Lucky numbers   " + "   ".join(str(n) for n in self.numbers)
        ImageDraw.Draw(out).text((W / 2, base), nums, font=self.small(s), fill=co_mix(paper, ink, 0.55) + (255,),
                                 anchor="ms")
        self.drawn = (key, out, None)
        return out

    def cookie(self, t, s):
        """The cookie as it is t of the way open (kept: a few steps of it)."""
        step = round(t * 20)
        key = (FORTUNE_COOKIE, s, step)
        if key not in self.pictures:
            if len(self.pictures) > 48:
                self.pictures.clear()
            self.pictures[key] = cookie_picture(FORTUNE_COOKIE, step / 20, s)
        return self.pictures[key]

    def draw(self, img, x0, y0, now=None):
        s = detail(img)
        pic = img.pic if s > 1 else img
        W, H = self.w * s, self.h * s
        wall = time.time() if now is None else now
        t = self.cracking(wall)
        words = self.picture(W, H, s)
        if t >= 1.0:
            pic.paste(words, (x0 * s, y0 * s), words)
        elif t > 0.45:                                 # (its fortune comes in as the cookie opens)
            f = (t - 0.45) / 0.55
            pic.paste(words, (x0 * s, y0 * s), words.getchannel("A").point(lambda v: int(v * f)))
        cookie = self.cookie(t, s)
        cy = self.layout(H, s)[0]
        pic.paste(cookie, (x0 * s + (W - cookie.width) // 2, y0 * s + int(cy - cookie.height / 2)), cookie)
