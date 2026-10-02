// Package codex reads Codex sessions from two places:
//
//   - the shared app-server daemon (what `codex agents` browses), via
//     `codex app-server proxy`, using only read-only JSON-RPC methods;
//   - running `codex` processes, matched to their rollout JSONL under
//     ~/.codex/sessions, whose tail tells us busy vs idle.
//
// It never reads auth.json and never sends a mutating method.
package codex

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"github.com/hiteshbandhu/hallmonitor/internal/model"
	"github.com/hiteshbandhu/hallmonitor/internal/proc"
)

type Adapter struct {
	Home string // defaults to $HOME
}

func (Adapter) Name() string { return "codex" }

func (a Adapter) codexHome() string {
	if v := os.Getenv("CODEX_HOME"); v != "" {
		return v
	}
	home := a.Home
	if home == "" {
		home, _ = os.UserHomeDir()
	}
	return filepath.Join(home, ".codex")
}

func (a Adapter) Collect(ctx context.Context) ([]model.Session, error) {
	home := a.codexHome()
	titles := readSessionIndex(filepath.Join(home, "session_index.jsonl"))

	var errs []error
	byID := map[string]*model.Session{}
	var order []string
	add := func(s model.Session) {
		if cur, ok := byID[s.ID]; ok && s.ID != "" {
			mergeInto(cur, s)
			return
		}
		cp := s
		key := s.ID
		if key == "" {
			key = "pid:" + strconv.Itoa(s.PID)
		}
		byID[key] = &cp
		order = append(order, key)
	}

	daemon, err := daemonThreads(ctx, home)
	if err != nil && !errors.Is(err, errNoDaemon) {
		errs = append(errs, err)
	}
	for _, s := range daemon {
		add(s)
	}

	procs, err := processSessions(ctx, home)
	if err != nil {
		errs = append(errs, err)
	}
	for _, s := range procs {
		add(s)
	}

	out := make([]model.Session, 0, len(order))
	for _, k := range order {
		s := byID[k]
		if s.Title == "" {
			s.Title = titles[s.ID]
		}
		out = append(out, *s)
	}
	if len(out) == 0 && len(errs) > 0 {
		return nil, errors.Join(errs...)
	}
	return out, nil
}

// mergeInto fills gaps in dst from src. Daemon status wins over rollout
// heuristics because it's authoritative.
func mergeInto(dst *model.Session, src model.Session) {
	if dst.PID == 0 {
		dst.PID = src.PID
	}
	if dst.Title == "" {
		dst.Title = src.Title
	}
	if dst.CWD == "" {
		dst.CWD = src.CWD
	}
	if dst.Model == "" {
		dst.Model = src.Model
	}
	if dst.Last == "" {
		dst.Last = src.Last
	}
	if dst.Prompt == "" {
		dst.Prompt = src.Prompt
	}
	if dst.Since.IsZero() {
		dst.Since = src.Since
	}
	if len(dst.Activity) == 0 {
		dst.Activity = src.Activity
	}
	if dst.Status == model.StatusUnknown {
		dst.Status = src.Status
	}
	if src.UpdatedAt.After(dst.UpdatedAt) {
		dst.UpdatedAt = src.UpdatedAt
	}
	for k, v := range src.Extra {
		if _, ok := dst.Extra[k]; !ok {
			if dst.Extra == nil {
				dst.Extra = map[string]string{}
			}
			dst.Extra[k] = v
		}
	}
}

// processSessions finds live `codex` processes and describes each from its
// rollout file.
func processSessions(ctx context.Context, home string) ([]model.Session, error) {
	pctx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()
	procs, err := proc.List(pctx, "codex")
	if err != nil {
		return nil, err
	}
	var out []model.Session
	for _, p := range procs {
		// The daemon and our own proxy aren't sessions.
		if strings.Contains(p.Args, "app-server") || strings.Contains(p.Args, "exec-server") {
			continue
		}
		cwd, files, _ := proc.OpenFiles(pctx, p.PID)
		s := model.Session{
			Provider:  "codex",
			PID:       p.PID,
			CWD:       cwd,
			Kind:      kindFromArgs(p.Args),
			Status:    model.StatusIdle, // alive, no turn seen yet
			StartedAt: p.Started,
			Source:    "process",
			Extra:     map[string]string{},
		}
		rollout := ""
		for _, f := range files {
			if strings.HasPrefix(filepath.Base(f), "rollout-") && strings.HasSuffix(f, ".jsonl") {
				rollout = f
			}
		}
		if rollout == "" && cwd != "" {
			rollout = newestRolloutFor(filepath.Join(home, "sessions"), cwd, p.Started)
		}
		if rollout != "" {
			if r, err := readRollout(rollout); err == nil {
				s.ID = r.ID
				if r.Status != model.StatusUnknown {
					s.Status = r.Status
				}
				s.Last = r.Last
				s.Prompt = r.Prompt
				s.Since = r.Since
				s.Activity = r.Activity
				s.Model = r.Model
				s.StartedAt = r.StartedAt
				s.UpdatedAt = r.UpdatedAt
				s.Source = "rollout"
				if s.CWD == "" {
					s.CWD = r.CWD
				}
				if r.Originator != "" {
					s.Extra["originator"] = r.Originator
				}
			}
		}
		out = append(out, s)
	}
	return out, nil
}

func kindFromArgs(args string) string {
	f := strings.Fields(args)
	if len(f) > 1 {
		switch f[1] {
		case "exec", "e", "review":
			return "background"
		}
	}
	return "interactive"
}

func readSessionIndex(path string) map[string]string {
	out := map[string]string{}
	b, err := os.ReadFile(path)
	if err != nil {
		return out
	}
	for _, line := range strings.Split(string(b), "\n") {
		var e struct {
			ID   string `json:"id"`
			Name string `json:"thread_name"`
		}
		if json.Unmarshal([]byte(line), &e) == nil && e.ID != "" && e.Name != "" {
			out[e.ID] = e.Name
		}
	}
	return out
}
