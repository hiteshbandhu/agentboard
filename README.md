# agentboard

A live status wall for every coding agent you're running: Claude Code and Codex, on this machine and on your servers. Put it on a second display and see at a glance who's working, who's done, and who needs you.

![agentboard --demo](docs/demo.png)

```bash
go build -o bin/agentboard ./cmd/agentboard
bin/agentboard                 # the wall
bin/agentboard --demo          # synthetic fleet, to try it or take screenshots
bin/agentboard --host dev@gpu-box --host build-01
bin/agentboard --once          # table, exit
bin/agentboard --json          # snapshot for scripts
```

Keys: arrows/hjkl move · `f` cycle provider · `s` show stale sessions · `q` quit.

## Logos

Each card shows its provider's logo, drawn as a real image in the terminal. Nothing extra to install:

| Terminal | How it draws |
|---|---|
| Ghostty, cmux, kitty, WezTerm | crisp pixel image via the kitty graphics protocol (Unicode placeholders) |
| iTerm2, Terminal.app, anything truecolor | pixel-art approximation from colored half-block characters |
| no truecolor, or `--images off` | text marks: `✻ Claude`, `>_ Codex` |

agentboard ships no brand artwork. It finds logos at runtime, in this order:
1. the installed app's own icon: `Claude.app`, `Codex.app` or `ChatGPT.app`;
2. a copy cached from an earlier run;
3. for Claude, the mark from [Simple Icons](https://simpleicons.org) on jsDelivr (pinned to v16.33.0) on a clay tile, cached under your user cache directory. Simple Icons no longer carries OpenAI's mark, so Codex gets a plain `>_` tile drawn locally.

Pass `--no-fetch` to never touch the network, or `--images blocks|kitty|off` to override detection.

## Other machines

agentboard watches remote hosts over plain SSH. There's no daemon, no open port and no extra auth. It uses your `~/.ssh/config` and agent.

1. Install `agentboard` on the server (on its `PATH`, or pass `--remote-cmd /path/to/agentboard`).
2. Add the host with `--host user@server`, or list hosts one per line in `~/.config/agentboard/hosts`.

Each host keeps one SSH connection open and streams `agentboard --stream` snapshots over it. If the connection drops, it reconnects with backoff. Unreachable hosts turn red in the top bar.

## Where the data comes from

| Provider | Source | Status |
|---|---|---|
| Claude Code | `claude agents --json`, `~/.claude/sessions/<pid>.json`, tail of the session transcript (latest tool, prompt, context size) | working / idle / blocked |
| Codex | shared app-server daemon via `codex app-server proxy`, read-only `thread/list` | working / needs you / idle / error |
| Codex | live `codex` processes and the rollout JSONL they hold open | working / idle / error |

agentboard is read-only. It never sends prompts, approvals or mutating RPCs. It never reads `auth.json` or Claude's `.key` files, and it doesn't connect to Claude's messaging sockets. Prompt and tool snippets are capped at about 120 characters.
