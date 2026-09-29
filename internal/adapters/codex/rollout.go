package codex

import (
	"bufio"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/hiteshbandhu/agentboard/internal/model"
)

type rollout struct {
	ID         string
	CWD        string
	Originator string
	Model      string
	Status     model.Status
	Last       string
	Prompt     string
	Since      time.Time
	Activity   []int64
	StartedAt  time.Time
	UpdatedAt  time.Time
}

type rolloutLine struct {
	Timestamp string          `json:"timestamp"`
	Type      string          `json:"type"`
	Payload   json.RawMessage `json:"payload"`
}

type sessionMeta struct {
	ID         string `json:"id"`
	Timestamp  string `json:"timestamp"`
	CWD        string `json:"cwd"`
	Originator string `json:"originator"`
}

// readRollout parses the session_meta header and the last ~256KB of a rollout.
func readRollout(path string) (rollout, error) {
	f, err := os.Open(path)
	if err != nil {
		return rollout{}, err
	}
	defer f.Close()
	var r rollout
	r.Status = model.StatusUnknown

	// Header: the first line is session_meta. It embeds base instructions, so
	// it can be long.
	br := bufio.NewReaderSize(f, 64*1024)
	head, err := br.ReadBytes('\n')
	if err != nil && err != io.EOF {
		return r, err
	}
	var hl rolloutLine
	if json.Unmarshal(head, &hl) == nil && hl.Type == "session_meta" {
		var m sessionMeta
		if json.Unmarshal(hl.Payload, &m) == nil {
			r.ID, r.CWD, r.Originator = m.ID, m.CWD, m.Originator
			r.StartedAt = parseTS(m.Timestamp)
		}
	}
	if r.ID == "" {
		r.ID = idFromRolloutName(path)
	}
	if st, err := f.Stat(); err == nil {
		r.UpdatedAt = st.ModTime()
	}

	// Tail.
	const tail = 256 * 1024
	st, err := f.Stat()
	if err != nil {
		return r, nil
	}
	off := max(st.Size()-tail, 0)
	buf := make([]byte, st.Size()-off)
	if _, err := f.ReadAt(buf, off); err != nil && err != io.EOF {
		return r, nil
	}
	lines := strings.Split(string(buf), "\n")
	if off > 0 && len(lines) > 0 {
		lines = lines[1:] // partial first line
	}
	for _, l := range lines {
		applyLine(&r, l)
	}
	return r, nil
}

func applyLine(r *rollout, l string) {
	if l == "" {
		return
	}
	var rl rolloutLine
	if json.Unmarshal([]byte(l), &rl) != nil {
		return
	}
	if rl.Type == "response_item" || rl.Type == "event_msg" {
		r.Activity = model.AddActivity(r.Activity, parseTS(rl.Timestamp), time.Now())
	}
	var p struct {
		Type  string `json:"type"`
		Name  string `json:"name"`
		Role  string `json:"role"`
		Model string `json:"model"`
		Error *struct {
			Message string `json:"message"`
		} `json:"error"`
		Item *struct {
			Type    string `json:"type"`
			Content []struct {
				Text string `json:"text"`
			} `json:"content"`
		} `json:"item"`
	}
	_ = json.Unmarshal(rl.Payload, &p)
	switch rl.Type {
	case "turn_context":
		if p.Model != "" {
			r.Model = p.Model
		}
	case "event_msg":
		switch p.Type {
		case "task_started":
			r.Status = model.StatusBusy
			r.Since = parseTS(rl.Timestamp)
		case "task_complete":
			r.Status = model.StatusIdle
			r.Since = parseTS(rl.Timestamp)
			if p.Error != nil && p.Error.Message != "" {
				r.Status = model.StatusError
				r.Last = "error: " + model.Snip(p.Error.Message, 110)
			}
		case "turn_aborted":
			r.Status = model.StatusIdle
			r.Since = parseTS(rl.Timestamp)
			r.Last = "turn aborted"
		case "item_completed":
			if p.Item != nil && p.Item.Type == "UserMessage" && len(p.Item.Content) > 0 {
				r.Prompt = model.Snip(p.Item.Content[0].Text, 120)
			}
		}
	case "response_item":
		// A long turn can start before the tail window; model output with no
		// turn marker seen yet means we're mid-turn.
		if r.Status == model.StatusUnknown {
			r.Status = model.StatusBusy
		}
		switch p.Type {
		case "custom_tool_call", "function_call":
			if p.Name != "" {
				r.Last = p.Name
			}
		}
	}
}

// newestRolloutFor finds the most recently modified rollout from the last few
// days whose session cwd matches and that was written after the process
// started. Used when the process has no rollout open.
func newestRolloutFor(sessionsDir, cwd string, since time.Time) string {
	var cands []string
	now := time.Now()
	for d := 0; d < 3; d++ {
		day := now.AddDate(0, 0, -d)
		dir := filepath.Join(sessionsDir, day.Format("2006"), day.Format("01"), day.Format("02"))
		m, _ := filepath.Glob(filepath.Join(dir, "rollout-*.jsonl"))
		cands = append(cands, m...)
	}
	type fm struct {
		p string
		t time.Time
	}
	var fs []fm
	for _, c := range cands {
		if st, err := os.Stat(c); err == nil && st.ModTime().After(since) {
			fs = append(fs, fm{c, st.ModTime()})
		}
	}
	sort.Slice(fs, func(i, j int) bool { return fs[i].t.After(fs[j].t) })
	for _, f := range fs {
		if metaCWD(f.p) == cwd {
			return f.p
		}
	}
	return ""
}

func metaCWD(path string) string {
	f, err := os.Open(path)
	if err != nil {
		return ""
	}
	defer f.Close()
	head, _ := bufio.NewReaderSize(f, 64*1024).ReadBytes('\n')
	var rl rolloutLine
	if json.Unmarshal(head, &rl) != nil {
		return ""
	}
	var m sessionMeta
	_ = json.Unmarshal(rl.Payload, &m)
	return m.CWD
}

// rollout-2026-09-28T00-54-13-<uuid>.jsonl -> <uuid>
func idFromRolloutName(path string) string {
	b := strings.TrimSuffix(filepath.Base(path), ".jsonl")
	if len(b) >= 36 {
		return b[len(b)-36:]
	}
	return ""
}

func parseTS(s string) time.Time {
	t, _ := time.Parse(time.RFC3339Nano, s)
	return t
}
