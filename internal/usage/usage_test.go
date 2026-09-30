package usage

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const claudeFixture = `{"type":"user","timestamp":"2026-09-29T10:00:00Z","sessionId":"s1","cwd":"/x/proj","message":{"content":"fix the bug"}}
{"type":"assistant","timestamp":"2026-09-29T10:00:05Z","sessionId":"s1","cwd":"/x/proj","requestId":"r1","message":{"id":"m1","model":"claude-opus-5-5","content":[{"type":"thinking"}],"usage":{"input_tokens":10,"cache_read_input_tokens":1000,"cache_creation_input_tokens":50,"output_tokens":20}}}
{"type":"assistant","timestamp":"2026-09-29T10:00:06Z","sessionId":"s1","cwd":"/x/proj","requestId":"r1","message":{"id":"m1","model":"claude-opus-5-5","content":[{"type":"tool_use","name":"Bash"}],"usage":{"input_tokens":10,"cache_read_input_tokens":1000,"cache_creation_input_tokens":50,"output_tokens":20}}}
{"type":"user","timestamp":"2026-09-29T10:00:30Z","sessionId":"s1","cwd":"/x/proj","message":{"content":[{"type":"tool_result"}]}}
`

const claudeMore = `{"type":"assistant","timestamp":"2026-09-29T10:01:00Z","sessionId":"s1","cwd":"/x/proj","requestId":"r2","message":{"id":"m2","model":"claude-opus-5-5","content":[{"type":"text","text":"done"}],"usage":{"input_tokens":5,"cache_read_input_tokens":2000,"cache_creation_input_tokens":0,"output_tokens":40}}}
`

const codexFixture = `{"timestamp":"2026-09-29T11:00:00Z","type":"session_meta","payload":{"id":"c1","cwd":"/y/svc/.kandy/worktrees/n1"}}
{"timestamp":"2026-09-29T11:00:01Z","type":"turn_context","payload":{"model":"gpt-6-astra"}}
{"timestamp":"2026-09-29T11:00:02Z","type":"event_msg","payload":{"type":"item_completed","item":{"type":"UserMessage"}}}
{"timestamp":"2026-09-29T11:00:10Z","type":"response_item","payload":{"type":"function_call","name":"exec"}}
{"timestamp":"2026-09-29T11:00:11Z","type":"token_usage_record","payload":{"response_id":"resp1","usage":{"input_tokens":1000,"cached_input_tokens":600,"output_tokens":30}}}
{"timestamp":"2026-09-29T11:00:11Z","type":"token_usage_record","payload":{"response_id":"resp1","usage":{"input_tokens":1000,"cached_input_tokens":600,"output_tokens":30}}}
{"timestamp":"2026-09-29T11:00:12Z","type":"event_msg","payload":{"type":"token_count","rate_limits":{"primary":{"used_percent":12.5,"window_minutes":300,"resets_at":1790700000}}}}
`

// The fixtures are written against a fixed hour; recent moves them to an hour
// ago, because the ledger forgets sessions it hasn't heard from in a day.
var base = time.Now().UTC().Add(-time.Hour).Truncate(time.Hour)

func recent(s string) string {
	at := base.Format("2006-01-02T15:")
	return strings.NewReplacer("2026-09-29T10:", at, "2026-09-29T11:", at).Replace(s)
}

func setup(t *testing.T) (*Ledger, string) {
	home := t.TempDir()
	cdir := filepath.Join(home, ".claude", "projects", "-x-proj")
	xdir := filepath.Join(home, ".codex", "sessions", "2026", "09", "29")
	for _, d := range []string{cdir, xdir} {
		if err := os.MkdirAll(d, 0o755); err != nil {
			t.Fatal(err)
		}
	}
	cf := filepath.Join(cdir, "s1.jsonl")
	os.WriteFile(cf, []byte(recent(claudeFixture)), 0o644)
	os.WriteFile(filepath.Join(xdir, "rollout-2026-09-29T11-00-00-c1.jsonl"), []byte(recent(codexFixture)), 0o644)
	l := &Ledger{Dir: filepath.Join(home, "ledger"), Home: home}
	return l, cf
}

func TestLedger(t *testing.T) {
	l, cf := setup(t)
	if err := l.Update(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
	// Append more, and re-run: only the new line is read, dup ids stay deduped.
	f, _ := os.OpenFile(cf, os.O_APPEND|os.O_WRONLY, 0)
	f.WriteString(recent(claudeMore))
	f.Close()
	if err := l.Update(context.Background(), nil); err != nil {
		t.Fatal(err)
	}
	if err := l.Update(context.Background(), nil); err != nil { // no-op
		t.Fatal(err)
	}

	d := l.day(base.Local().Format("2006-01-02"))
	var claude, codex Counters
	for k, c := range d.Buckets {
		switch {
		case contains(k, "|claude|"):
			claude.Add(*c)
		case contains(k, "|codex|"):
			codex.Add(*c)
		}
	}
	if got := claude.Tokens; got != (Tokens{Input: 15, CacheRead: 3000, CacheWrite: 50, Output: 60}) {
		t.Errorf("claude tokens = %+v", got)
	}
	if claude.Replies != 2 || claude.Prompts != 1 || claude.Tools != 1 {
		t.Errorf("claude counts = %+v", claude)
	}
	if claude.Active != 60 { // 10:00:00 → 10:01:00, all gaps under 5m
		t.Errorf("claude active = %v", claude.Active)
	}
	if got := codex.Tokens; got != (Tokens{Input: 400, CacheRead: 600, Output: 30}) {
		t.Errorf("codex tokens = %+v", got)
	}
	if codex.Replies != 1 || codex.Prompts != 1 || codex.Tools != 1 {
		t.Errorf("codex counts = %+v", codex)
	}
	if _, ok := d.Sessions["c1"]; !ok {
		t.Error("codex session missing")
	}
	for k := range d.Buckets {
		if contains(k, "|codex|") && !contains(k, "|svc|") {
			t.Errorf("worktree didn't roll up to repo: %s", k)
		}
	}
	if rl := l.st.RateLimits["codex"]; rl.UsedPercent != 12.5 || rl.WindowMin != 300 {
		t.Errorf("rate limit = %+v", rl)
	}
}

func contains(s, sub string) bool { return strings.Contains(s, sub) }
