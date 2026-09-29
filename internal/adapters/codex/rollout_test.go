package codex

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/hiteshbandhu/agentboard/internal/model"
)

func TestReadRollout(t *testing.T) {
	cases := []struct {
		file   string
		status model.Status
		last   string
		model  string
	}{
		{"busy.jsonl", model.StatusBusy, "apply_patch", "gpt-6-astra"},
		{"error.jsonl", model.StatusError, "error: token revoked", ""},
	}
	for _, c := range cases {
		r, err := readRollout(filepath.Join("testdata", c.file))
		if err != nil {
			t.Fatal(err)
		}
		if r.Status != c.status || r.Last != c.last || r.Model != c.model || r.CWD != "/tmp/proj" {
			t.Errorf("%s: got %+v", c.file, r)
		}
	}
}

// TestRealRollouts parses this machine's recent rollouts, if any, to catch
// format drift. It only checks that parsing yields an id and a status.
func TestRealRollouts(t *testing.T) {
	home, _ := os.UserHomeDir()
	files, _ := filepath.Glob(filepath.Join(home, ".codex", "sessions", "*", "*", "*", "rollout-*.jsonl"))
	if len(files) == 0 {
		t.Skip("no local rollouts")
	}
	if len(files) > 20 {
		files = files[len(files)-20:]
	}
	for _, f := range files {
		r, err := readRollout(f)
		if err != nil {
			t.Errorf("%s: %v", f, err)
			continue
		}
		if r.ID == "" || r.Status == model.StatusUnknown {
			t.Errorf("%s: id=%q status=%s", filepath.Base(f), r.ID, r.Status)
		}
		t.Logf("%s %s %q", r.ID[:8], r.Status, r.Last)
	}
}

func TestThreadStatus(t *testing.T) {
	if threadStatus("active", []string{"waitingOnApproval"}) != model.StatusWaiting {
		t.Error("approval should be waiting")
	}
	if threadStatus("active", nil) != model.StatusBusy {
		t.Error("active should be busy")
	}
	if threadStatus("notLoaded", nil) != model.StatusUnknown {
		t.Error("notLoaded should be unknown")
	}
}
