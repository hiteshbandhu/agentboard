package main

import (
	"context"
	"flag"
	"fmt"
	"os"

	"github.com/hiteshbandhu/agentboard/internal/focus"
)

// runFocus is `agentboard focus`: bring an agent's window to the front. The
// menu bar app calls it when you click an agent.
func runFocus(ctx context.Context, args []string) {
	fs := flag.NewFlagSet("focus", flag.ExitOnError)
	var t focus.Target
	fs.StringVar(&t.Host, "host", "", "machine the agent runs on (empty: this one)")
	fs.StringVar(&t.Provider, "provider", "", "claude or codex")
	fs.StringVar(&t.ID, "id", "", "session id")
	fs.IntVar(&t.PID, "pid", 0, "agent process id")
	fs.StringVar(&t.Entrypoint, "entrypoint", "", "Claude Code entrypoint (claude-desktop, cli, …)")
	_ = fs.Parse(args)
	where, err := focus.Focus(ctx, t)
	if err != nil {
		fmt.Fprintln(os.Stderr, "agentboard: focus:", err)
		os.Exit(1)
	}
	fmt.Println(where)
}
