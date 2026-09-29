package codex

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/hiteshbandhu/agentboard/internal/model"
)

var errNoDaemon = errors.New("codex app-server daemon not running")

// readOnlyMethods is the full set of methods agentboard may send. Anything
// else is refused before it reaches the wire.
var readOnlyMethods = map[string]bool{
	"initialize":         true,
	"initialized":        true,
	"thread/list":        true,
	"thread/loaded/list": true,
}

type rpcThread struct {
	ID         string  `json:"id"`
	Name       *string `json:"name"`
	CWD        string  `json:"cwd"`
	Model      *string `json:"model"`
	Preview    string  `json:"preview"`
	Source     any     `json:"source"`
	Originator *string `json:"originator"`
	CreatedAt  int64   `json:"createdAt"`
	UpdatedAt  int64   `json:"updatedAt"`
	Status     struct {
		Type        string   `json:"type"`
		ActiveFlags []string `json:"activeFlags"`
	} `json:"status"`
}

// daemonThreads asks the shared daemon for threads that are loaded right now.
// It goes through `codex app-server proxy` so we don't depend on the socket's
// framing, and it only runs when the control socket exists.
func daemonThreads(ctx context.Context, home string) ([]model.Session, error) {
	sock := filepath.Join(home, "app-server-control", "app-server-control.sock")
	if _, err := os.Stat(sock); err != nil {
		return nil, errNoDaemon
	}
	ctx, cancel := context.WithTimeout(ctx, 4*time.Second)
	defer cancel()

	cmd := exec.CommandContext(ctx, "codex", "app-server", "proxy", "--sock", sock)
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	if err := cmd.Start(); err != nil {
		return nil, fmt.Errorf("codex proxy: %w", err)
	}
	defer func() {
		stdin.Close()
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
	}()

	enc := json.NewEncoder(stdin)
	send := func(id int, method string, params any) error {
		if !readOnlyMethods[method] {
			return fmt.Errorf("refusing non-read-only method %q", method)
		}
		msg := map[string]any{"method": method}
		if id > 0 {
			msg["id"] = id
		}
		if params != nil {
			msg["params"] = params
		}
		return enc.Encode(msg)
	}

	sc := bufio.NewScanner(stdout)
	sc.Buffer(make([]byte, 1024*1024), 32*1024*1024)
	wait := func(id int) (json.RawMessage, error) {
		for sc.Scan() {
			var m struct {
				ID     *int            `json:"id"`
				Result json.RawMessage `json:"result"`
				Error  *struct {
					Message string `json:"message"`
				} `json:"error"`
			}
			if json.Unmarshal(sc.Bytes(), &m) != nil || m.ID == nil || *m.ID != id {
				continue // notifications
			}
			if m.Error != nil {
				return nil, fmt.Errorf("codex daemon: %s", m.Error.Message)
			}
			return m.Result, nil
		}
		if err := sc.Err(); err != nil {
			return nil, err
		}
		return nil, fmt.Errorf("codex daemon: connection closed")
	}

	if err := send(1, "initialize", map[string]any{
		"clientInfo": map[string]string{"name": "agentboard", "version": "0.1.0"},
	}); err != nil {
		return nil, err
	}
	if _, err := wait(1); err != nil {
		return nil, err
	}
	_ = send(0, "initialized", nil)
	if err := send(2, "thread/list", map[string]any{
		"limit": 50, "sortKey": "updated_at",
	}); err != nil {
		return nil, err
	}
	raw, err := wait(2)
	if err != nil {
		return nil, err
	}
	var res struct {
		Data []rpcThread `json:"data"`
	}
	if err := json.Unmarshal(raw, &res); err != nil {
		return nil, err
	}

	var out []model.Session
	for _, t := range res.Data {
		if t.Status.Type == "" || t.Status.Type == "notLoaded" {
			continue // on disk only, not alive
		}
		s := model.Session{
			Provider:  "codex",
			ID:        t.ID,
			CWD:       t.CWD,
			Kind:      "daemon",
			Status:    threadStatus(t.Status.Type, t.Status.ActiveFlags),
			StartedAt: unix(t.CreatedAt),
			UpdatedAt: unix(t.UpdatedAt),
			Source:    "app-server",
			Extra:     map[string]string{},
		}
		if t.Name != nil {
			s.Title = *t.Name
		}
		if s.Title == "" {
			s.Title = model.Snip(t.Preview, 60)
		}
		if t.Model != nil {
			s.Model = *t.Model
		}
		if t.Originator != nil {
			s.Extra["originator"] = *t.Originator
		}
		for _, f := range t.Status.ActiveFlags {
			s.Last = f
		}
		out = append(out, s)
	}
	return out, nil
}

func threadStatus(typ string, flags []string) model.Status {
	switch typ {
	case "active":
		for _, f := range flags {
			if f == "waitingOnApproval" || f == "waitingOnUserInput" {
				return model.StatusWaiting
			}
		}
		return model.StatusBusy
	case "idle":
		return model.StatusIdle
	case "systemError":
		return model.StatusError
	}
	return model.StatusUnknown
}

func unix(v int64) time.Time {
	if v <= 0 {
		return time.Time{}
	}
	return time.Unix(v, 0)
}
