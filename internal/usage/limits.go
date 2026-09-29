package usage

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// Claude Code only exposes plan limits to status line scripts, so
// `agentboard statusline` saves them here as they go by.
func claudeLimitsPath(dir string) string { return filepath.Join(dir, "claude-limits.json") }

type claudeWindow struct {
	UsedPercent float64 `json:"used_percentage"`
	ResetsAt    int64   `json:"resets_at"`
}

// ClaudeStatus is the part of Claude Code's status line input we keep.
type ClaudeStatus struct {
	RateLimits struct {
		FiveHour   *claudeWindow `json:"five_hour"`
		SevenDay   *claudeWindow `json:"seven_day"`
		SpendLimit *claudeWindow `json:"spend_limit"`
	} `json:"rate_limits"`
}

// SaveClaudeLimits records the windows present in a status line payload.
// Windows missing from this payload keep their last reading.
func (l *Ledger) SaveClaudeLimits(st ClaudeStatus, now time.Time) error {
	limits := l.claudeLimits()
	put := func(key string, w *claudeWindow, window int) {
		if w == nil {
			return
		}
		limits[key] = RateLimit{
			Provider:    "claude",
			Window:      key[len("claude:"):],
			UsedPercent: w.UsedPercent,
			WindowMin:   window,
			ResetsAt:    time.Unix(w.ResetsAt, 0),
			ObservedAt:  now,
		}
	}
	put("claude:5h", st.RateLimits.FiveHour, 5*60)
	put("claude:7d", st.RateLimits.SevenDay, 7*24*60)
	put("claude:spend", st.RateLimits.SpendLimit, 0)
	if err := os.MkdirAll(l.Dir, 0o755); err != nil {
		return err
	}
	return writeJSON(claudeLimitsPath(l.Dir), limits)
}

func (l *Ledger) claudeLimits() map[string]RateLimit {
	m := map[string]RateLimit{}
	if b, err := os.ReadFile(claudeLimitsPath(l.Dir)); err == nil {
		_ = json.Unmarshal(b, &m)
	}
	// A window that has reset no longer says anything useful.
	for k, rl := range m {
		if !rl.ResetsAt.IsZero() && time.Now().After(rl.ResetsAt) {
			delete(m, k)
		}
	}
	return m
}
