package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"sort"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/hiteshbandhu/agentboard/internal/usage"
)

// runUsage is `agentboard usage`: update the ledger, print a summary.
func runUsage(ctx context.Context, args []string) {
	fs := flag.NewFlagSet("usage", flag.ExitOnError)
	days := fs.Int("days", 7, "how many days, today included")
	asJSON := fs.Bool("json", false, "print JSON")
	noUpdate := fs.Bool("no-update", false, "don't read new agent logs first")
	_ = fs.Parse(args)

	l := usage.Open(usage.DefaultDir())
	if !*noUpdate {
		start := time.Now()
		last := time.Time{}
		err := l.Update(ctx, func(done, total int64) {
			if total > 64<<20 && time.Since(last) > 200*time.Millisecond {
				last = time.Now()
				fmt.Fprintf(os.Stderr, "\rindexing agent logs… %d%%", done*100/max(total, 1))
			}
		})
		if !last.IsZero() {
			fmt.Fprintf(os.Stderr, "\rindexed in %s            \n", time.Since(start).Round(100*time.Millisecond))
		}
		if err != nil && err != usage.ErrBusy {
			fmt.Fprintln(os.Stderr, "agentboard: usage:", err)
		}
	}
	s := l.Summarize(*days)
	if *asJSON {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		_ = enc.Encode(s)
		return
	}

	fmt.Printf("Agent usage, %s → %s\n\n", s.From, s.To)
	w := tabwriter.NewWriter(os.Stdout, 0, 2, 3, ' ', 0)
	fmt.Fprintln(w, "\tactive\tprompts\treplies\ttool calls\ttokens\tcache hit")
	provs := make([]string, 0, len(s.ByProvider))
	for p := range s.ByProvider {
		provs = append(provs, p)
	}
	sort.Strings(provs)
	row := func(name string, c usage.Counters) {
		fmt.Fprintf(w, "%s\t%s\t%d\t%d\t%d\t%s\t%s\n", name, Hours(c.Active), c.Prompts, c.Replies, c.Tools, Human(c.Tokens.Total()), cacheHit(c.Tokens))
	}
	for _, p := range provs {
		row(p, s.ByProvider[p])
	}
	row("total", s.Total)
	w.Flush()
	fmt.Printf("\n%d sessions\n", s.Sessions)

	list := func(title string, items []usage.Named, val func(usage.Counters) string) {
		if len(items) == 0 {
			return
		}
		fmt.Printf("\n%s\n", title)
		for _, n := range items[:min(5, len(items))] {
			fmt.Printf("  %-28s %s\n", n.Name, val(n.Counters))
		}
	}
	list("Top projects (active time)", s.Projects, func(c usage.Counters) string { return Hours(c.Active) })
	list("Top models (tokens)", s.Models, func(c usage.Counters) string { return Human(c.Tokens.Total()) })
	list("Top tools (calls)", s.Tools, func(c usage.Counters) string { return fmt.Sprint(c.Tools) })
	for _, rl := range s.RateLimits {
		fmt.Printf("\n%s plan: %.0f%% of %s window used, resets %s\n", rl.Provider, rl.UsedPercent,
			window(rl.WindowMin), rl.ResetsAt.Local().Format("Jan 2 15:04"))
	}
}

func Hours(sec float64) string {
	d := time.Duration(sec) * time.Second
	if d < time.Hour {
		return fmt.Sprintf("%dm", int(d.Minutes()))
	}
	return fmt.Sprintf("%.1fh", d.Hours())
}

func Human(n int64) string {
	switch {
	case n >= 1e9:
		return fmt.Sprintf("%.1fB", float64(n)/1e9)
	case n >= 1e6:
		return fmt.Sprintf("%.1fM", float64(n)/1e6)
	case n >= 1e3:
		return fmt.Sprintf("%.1fk", float64(n)/1e3)
	}
	return fmt.Sprint(n)
}

func cacheHit(t usage.Tokens) string {
	in := t.Input + t.CacheRead + t.CacheWrite
	if in == 0 {
		return "—"
	}
	return fmt.Sprintf("%.0f%%", float64(t.CacheRead)*100/float64(in))
}

func window(min int) string {
	switch {
	case min%(60*24) == 0:
		return fmt.Sprintf("%d-day", min/(60*24))
	case min%60 == 0:
		return fmt.Sprintf("%d-hour", min/60)
	}
	return strings.TrimSpace(fmt.Sprintf("%d-min", min))
}
