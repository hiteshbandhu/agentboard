package usage

import (
	"testing"
	"time"
)

// What /usage looks like once escape sequences are gone (Claude Code 2.1.285).
const usageScreen = ` Settings Status Config Usage Stats Session Total cost: $0.0000 Usage: 0 input, 0 output
 Current session ▌ 1% used Resets 6:20am (Asia/Calcutta) Current week (all models) █████████▌ 83% used
 Resets Oct 1 at 1:30am (Asia/Calcutta) What's contributing to your limits usage? Refreshing… Current session
 ▌ 2% used Resets 6:20am (Asia/Calcutta) Current week (Fable) 0% used Resets Oct 1 at 1:30am (Asia/Calcutta)`

func TestParseUsageScreen(t *testing.T) {
	ist, _ := time.LoadLocation("Asia/Calcutta")
	now := time.Date(2026, 9, 30, 23, 0, 0, 0, ist)
	got := parseUsageScreen(usageScreen, now)
	s, w := got["claude:5h"], got["claude:7d"]
	if s.UsedPercent != 2 || !s.ResetsAt.Equal(time.Date(2026, 10, 1, 6, 20, 0, 0, ist)) || s.WindowMin != 300 {
		t.Errorf("5h = %+v", s)
	}
	if w.UsedPercent != 83 || !w.ResetsAt.Equal(time.Date(2026, 10, 1, 1, 30, 0, 0, ist)) {
		t.Errorf("7d = %+v", w)
	}
	if len(parseUsageScreen("Usage credits are off", now)) != 0 {
		t.Error("found limits in a screen without any")
	}
}

func TestParseReset(t *testing.T) {
	utc := time.UTC
	now := time.Date(2026, 12, 30, 22, 0, 0, 0, utc)
	for in, want := range map[string]time.Time{
		"9pm":                 time.Date(2026, 12, 31, 21, 0, 0, 0, utc),
		"11:30pm":             time.Date(2026, 12, 30, 23, 30, 0, 0, utc),
		"12am":                time.Date(2026, 12, 31, 0, 0, 0, 0, utc),
		"Jan 2 at 1:30am":     time.Date(2027, 1, 2, 1, 30, 0, 0, utc),
		"Dec 31":              time.Date(2026, 12, 31, 0, 0, 0, 0, utc),
		"Mar 3, 2027 at 12pm": time.Date(2027, 3, 3, 12, 0, 0, 0, utc),
	} {
		if got := parseReset(in, "UTC", now); !got.Equal(want) {
			t.Errorf("%q = %v, want %v", in, got, want)
		}
	}
	if !parseReset("soon", "UTC", now).IsZero() {
		t.Error("parsed nonsense")
	}
}
