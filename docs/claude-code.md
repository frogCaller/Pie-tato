# Claude Code

Press right on the Bot to go from chatting to work. At work it sits at a desk: it
reads when your coding agent reads, types when it writes code, waves when it needs you, and rings a
bell when it's done.

To connect Claude Code, run this on the computer it runs on:

```
curl -O http://<your Pi's IP address>:5432/coder_hooks.py
python3 coder_hooks.py <your Pi's IP address>
```

It adds hooks to Claude Code's settings that tell the Pi what Claude Code is doing. They run in
the background and do nothing when the Pi is off. `--remove` takes them out again.

The same script lets you send Claude Code prompts from the Pi. Start Claude Code like this:

```
claude --dangerously-load-development-channels server:pitato
```

Then press A at work, type a prompt, and press START. Claude Code gets it as if you had typed it.
When Claude Code asks to use a tool (to run a command, say), the question shows on the Pi too: A allows
it, B denies it, and X leaves it for the computer. Whichever answers first counts.
This uses Claude Code's channels, which are a research preview: Claude Code asks you to confirm
each time it starts, and it needs to be signed in with a Claude account or an Anthropic API key.
If channels aren't available to you yet, Claude Code says so when it starts.

- If your web page has a password, add `--password` and the password.
- Prompts and answers only come from the Pi itself. The web page's remote can't send them.
- If you only want the hooks, add `--no-prompts`.
- To have Claude Code use your Ollama models, start it with `ollama launch claude`
  ([Ollama's guide](https://docs.ollama.com/integrations/claude-code)). Prompts from the Pi
  need Claude Code signed in, though.
- Other agents and scripts can `POST /coder?pose=typing` (or `reading`, `thinking`, `done`...),
  and send a WAV to `POST /coder/say` to have it said out loud.

At work, A types a prompt, Y rings the bell, X turns its sounds off, and START shows these steps.
