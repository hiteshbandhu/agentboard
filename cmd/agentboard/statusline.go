package main

import (
	"bytes"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/hiteshbandhu/agentboard/internal/usage"
)

// runStatusline is `agentboard statusline`, meant to be Claude Code's
// statusLine command. It saves the plan limits Claude Code passes in (the
// only place they're exposed), then prints a status line: its own, or the
// output of --then, which gets the same input, so an existing status line
// keeps working.
func runStatusline(args []string) {
	fs := flag.NewFlagSet("statusline", flag.ExitOnError)
	then := fs.String("then", "", "run this status line command too, and print its output instead")
	_ = fs.Parse(args)

	in, _ := io.ReadAll(io.LimitReader(os.Stdin, 4<<20))
	var st usage.ClaudeStatus
	if json.Unmarshal(in, &st) == nil {
		_ = usage.Open(usage.DefaultDir()).SaveClaudeLimits(st, time.Now())
	}

	if *then != "" {
		cmd := exec.Command("/bin/sh", "-c", *then)
		cmd.Stdin = bytes.NewReader(in)
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		_ = cmd.Run()
		return
	}
	fmt.Println(ownStatusline(in))
}

func ownStatusline(in []byte) string {
	var d struct {
		Model struct {
			DisplayName string `json:"display_name"`
		} `json:"model"`
		ContextWindow struct {
			UsedPercentage *float64 `json:"used_percentage"`
		} `json:"context_window"`
		RateLimits map[string]struct {
			UsedPercentage float64 `json:"used_percentage"`
		} `json:"rate_limits"`
	}
	_ = json.Unmarshal(in, &d)
	parts := []string{"\x1b[38;2;217;119;87m✻\x1b[0m " + d.Model.DisplayName}
	if p := d.ContextWindow.UsedPercentage; p != nil {
		parts = append(parts, fmt.Sprintf("ctx %s", pct(*p)))
	}
	for _, w := range []struct{ key, label string }{{"five_hour", "5h"}, {"seven_day", "7d"}} {
		if rl, ok := d.RateLimits[w.key]; ok {
			parts = append(parts, fmt.Sprintf("%s %s", w.label, pct(rl.UsedPercentage)))
		}
	}
	return strings.Join(parts, " \x1b[2m·\x1b[0m ")
}

// pct colors a percentage green, amber past 50, red past 80.
func pct(p float64) string {
	c := "74;222;128"
	switch {
	case p >= 80:
		c = "248;113;113"
	case p >= 50:
		c = "251;191;36"
	}
	return fmt.Sprintf("\x1b[38;2;%sm%.0f%%\x1b[0m", c, p)
}
