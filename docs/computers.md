# Other computers

If you want another computer's files on the Pi, open Files, then Other computers, and add it by its
address (like `192.168.1.20`). On Windows or a Mac, share a folder first; on Linux, turn on SSH. Its
files open read-only, so nothing on that computer is changed from the Pi. To keep a copy on the Pi,
press SELECT on a file (in its list, or while you're looking at it), or Save to the Pi on the web page:
pictures go in Pictures, videos in Videos, music in Music, games in Games and the rest in Documents.

If you have more than one Pietato on your network, they share what they fetch: coin and stock prices
and charts, and the weather. Whichever needs something first fetches it, and the others ask it, so
CoinGecko and Yahoo Finance see one Pietato instead of several. Your game saves follow you too: when you
stop playing, that Pietato passes the game's saves to the others that are on, and when you start a game,
it checks the others for a newer save first. A save that gets replaced is kept in `Games/Saves/.replaced`.
Settings > Share with other Pietatos turns all of this off.
