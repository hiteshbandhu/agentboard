package usage

import (
	"bytes"
	"encoding/json"
	"path/filepath"
	"strings"
	"time"
)

// ---- Claude Code ----

func (l *Ledger) claudeFiles() []string {
	root := filepath.Join(l.Home, ".claude", "projects")
	a, _ := filepath.Glob(filepath.Join(root, "*", "*.jsonl"))
	b, _ := filepath.Glob(filepath.Join(root, "*", "*", "subagents", "*.jsonl"))
	probe := filepath.Join(root, EscapeProject(ProbeDir())) + string(filepath.Separator)
	var out []string
	for _, f := range append(a, b...) {
		if !strings.HasPrefix(f, probe) { // hallmonitor's own /usage probe
			out = append(out, f)
		}
	}
	return out
}

type claudeLine struct {
	Type      string `json:"type"`
	Timestamp string `json:"timestamp"`
	SessionID string `json:"sessionId"`
	CWD       string `json:"cwd"`
	IsMeta    bool   `json:"isMeta"`
	RequestID string `json:"requestId"`
	Message   struct {
		ID      string          `json:"id"`
		Model   string          `json:"model"`
		Content json.RawMessage `json:"content"`
		Usage   *struct {
			Input       int64 `json:"input_tokens"`
			CacheRead   int64 `json:"cache_read_input_tokens"`
			CacheCreate int64 `json:"cache_creation_input_tokens"`
			Output      int64 `json:"output_tokens"`
		} `json:"usage"`
	} `json:"message"`
}

// scanClaude reads transcript lines. A reply is split over several lines
// (one per content block) that repeat the same usage, so each
// (message id, request id) is counted once. Subagent transcripts carry the
// parent's sessionId, so their tokens land on the parent session.
func (l *Ledger) scanClaude(path string, fs *fileState, data []byte) error {
	seen := seenSet(fs)
	for _, line := range bytes.Split(data, []byte("\n")) {
		if len(line) == 0 {
			continue
		}
		// Cheap prefilter: skip summaries, snapshots and the like.
		if !bytes.Contains(line, []byte(`"type":"assistant"`)) && !bytes.Contains(line, []byte(`"type":"user"`)) {
			continue
		}
		var cl claudeLine
		if json.Unmarshal(line, &cl) != nil {
			continue
		}
		at, _ := time.Parse(time.RFC3339Nano, cl.Timestamp)
		e := event{at: at, provider: "claude", session: cl.SessionID, project: project(cl.CWD), active: true}
		switch cl.Type {
		case "user":
			var s string
			if !cl.IsMeta && json.Unmarshal(cl.Message.Content, &s) == nil && humanPrompt(s) {
				e.c.Prompts = 1
			}
		case "assistant":
			model := cl.Message.Model
			if model == "" || strings.HasPrefix(model, "<") {
				continue // synthetic messages
			}
			e.model = model
			id := cl.Message.ID + "|" + cl.RequestID
			first := !seen[id]
			if first {
				remember(fs, seen, id)
				if u := cl.Message.Usage; u != nil {
					e.c.Tokens = Tokens{Input: u.Input, CacheRead: u.CacheRead, CacheWrite: u.CacheCreate, Output: u.Output}
				}
				e.c.Replies = 1
			}
			var blocks []struct {
				Type string `json:"type"`
				Name string `json:"name"`
			}
			_ = json.Unmarshal(cl.Message.Content, &blocks)
			for _, b := range blocks {
				if b.Type == "tool_use" && b.Name != "" {
					e.tools = append(e.tools, toolName(b.Name))
					e.c.Tools++
				}
			}
		default:
			continue
		}
		l.record(e)
	}
	return nil
}

func humanPrompt(s string) bool {
	s = strings.TrimSpace(s)
	return s != "" && !strings.HasPrefix(s, "<") && !strings.HasPrefix(s, "Caveat:")
}

// toolName shortens MCP tool names to server·tool.
func toolName(n string) string {
	if strings.HasPrefix(n, "mcp__") {
		parts := strings.Split(n, "__")
		if len(parts) >= 3 {
			return parts[len(parts)-1]
		}
	}
	return n
}

func project(cwd string) string {
	if cwd == "" {
		return "?"
	}
	// Worktrees roll up to their repo: …/repo/.claude/worktrees/x, …/repo/.kandy/worktrees/x
	for _, marker := range []string{"/.claude/worktrees/", "/.kandy/worktrees/", "/.worktrees/"} {
		if i := strings.Index(cwd, marker); i > 0 {
			cwd = cwd[:i]
		}
	}
	return filepath.Base(cwd)
}

// ---- Codex ----

func (l *Ledger) codexFiles() []string {
	root := filepath.Join(l.Home, ".codex")
	a, _ := filepath.Glob(filepath.Join(root, "sessions", "*", "*", "*", "rollout-*.jsonl"))
	b, _ := filepath.Glob(filepath.Join(root, "archived_sessions", "rollout-*.jsonl"))
	return append(a, b...)
}

type codexLine struct {
	Timestamp string          `json:"timestamp"`
	Type      string          `json:"type"`
	Payload   json.RawMessage `json:"payload"`
}

type codexUsage struct {
	Input     int64 `json:"input_tokens"`
	Cached    int64 `json:"cached_input_tokens"`
	CacheW    int64 `json:"cache_write_input_tokens"`
	Output    int64 `json:"output_tokens"`
	Reasoning int64 `json:"reasoning_output_tokens"`
}

// scanCodex reads rollout lines. Token usage comes from token_usage_record
// (one per model response, deduped by response id). Codex counts cached
// input inside input_tokens, so it's split out to match Claude's shape.
func (l *Ledger) scanCodex(path string, fs *fileState, data []byte) error {
	if fs.Ctx == nil {
		fs.Ctx = map[string]string{}
	}
	seen := seenSet(fs)
	for _, line := range bytes.Split(data, []byte("\n")) {
		if len(line) == 0 {
			continue
		}
		var cl codexLine
		if json.Unmarshal(line, &cl) != nil {
			continue
		}
		at, _ := time.Parse(time.RFC3339Nano, cl.Timestamp)
		var p struct {
			Type       string      `json:"type"`
			ID         string      `json:"id"`
			SessionID  string      `json:"session_id"`
			CWD        string      `json:"cwd"`
			Model      string      `json:"model"`
			Name       string      `json:"name"`
			ResponseID string      `json:"response_id"`
			Usage      *codexUsage `json:"usage"`
			Item       *struct {
				Type string `json:"type"`
			} `json:"item"`
			RateLimits *struct {
				Primary *struct {
					UsedPercent float64 `json:"used_percent"`
					WindowMin   int     `json:"window_minutes"`
					ResetsAt    int64   `json:"resets_at"`
				} `json:"primary"`
			} `json:"rate_limits"`
		}
		_ = json.Unmarshal(cl.Payload, &p)

		e := event{at: at, provider: "codex", session: fs.Ctx["session"], project: fs.Ctx["project"], model: fs.Ctx["model"]}
		switch cl.Type {
		case "session_meta":
			fs.Ctx["session"] = firstNonEmpty(p.SessionID, p.ID)
			fs.Ctx["project"] = project(p.CWD)
			continue
		case "turn_context":
			if p.Model != "" {
				fs.Ctx["model"] = p.Model
			}
			continue
		case "token_usage_record":
			if p.Usage == nil || p.ResponseID == "" || seen[p.ResponseID] {
				continue
			}
			remember(fs, seen, p.ResponseID)
			u := p.Usage
			e.c.Tokens = Tokens{Input: max(0, u.Input-u.Cached), CacheRead: u.Cached, CacheWrite: u.CacheW, Output: u.Output}
			e.c.Replies = 1
			e.active = true
		case "response_item":
			if p.Type == "function_call" || p.Type == "custom_tool_call" {
				if p.Name != "" {
					e.tools = []string{p.Name}
					e.c.Tools = 1
				}
			}
			e.active = true
		case "event_msg":
			switch p.Type {
			case "item_completed":
				if p.Item != nil && p.Item.Type == "UserMessage" {
					e.c.Prompts = 1
				}
			case "token_count":
				if rl := p.RateLimits; rl != nil && rl.Primary != nil {
					prev := l.st.RateLimits["codex"]
					if at.After(prev.ObservedAt) {
						l.st.RateLimits["codex"] = RateLimit{
							Provider:    "codex",
							UsedPercent: rl.Primary.UsedPercent,
							WindowMin:   rl.Primary.WindowMin,
							ResetsAt:    time.Unix(rl.Primary.ResetsAt, 0),
							ObservedAt:  at,
						}
					}
				}
			}
			e.active = true
		default:
			continue
		}
		l.record(e)
	}
	return nil
}

func firstNonEmpty(v ...string) string {
	for _, s := range v {
		if s != "" {
			return s
		}
	}
	return ""
}
