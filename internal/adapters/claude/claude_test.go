package claude

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/hiteshbandhu/hallmonitor/internal/model"
)

func TestSessionFileWaiting(t *testing.T) {
	dir := t.TempDir()
	body := `{"pid":4242,"sessionId":"abc","cwd":"/tmp/p","kind":"interactive","name":"refactor",
		"status":"waiting","waitingFor":"permission to run Bash","updatedAt":1790000000000,"statusUpdatedAt":1790000000000}`
	if err := os.WriteFile(filepath.Join(dir, "4242.json"), []byte(body), 0o644); err != nil {
		t.Fatal(err)
	}
	// A key file sitting next to it must be ignored.
	_ = os.WriteFile(filepath.Join(dir, "4242.deadbeef.key"), []byte("secret"), 0o600)

	files := readSessionFiles(dir)
	if len(files) != 1 {
		t.Fatalf("read %d files, want 1", len(files))
	}
	s := model.Session{Extra: map[string]string{}}
	applyFile(&s, files[4242])
	if s.Status != model.StatusWaiting {
		t.Errorf("status = %s, want waiting", s.Status)
	}
	if s.Extra["waiting_for"] != "permission to run Bash" {
		t.Errorf("waiting_for = %q", s.Extra["waiting_for"])
	}
}

func TestMapStatus(t *testing.T) {
	cases := map[[2]string]model.Status{
		{"busy", ""}:    model.StatusBusy,
		{"idle", ""}:    model.StatusIdle,
		{"waiting", ""}: model.StatusWaiting,
		{"", "blocked"}: model.StatusBlocked,
		{"", ""}:        model.StatusUnknown,
	}
	for in, want := range cases {
		if got := mapStatus(in[0], in[1]); got != want {
			t.Errorf("mapStatus(%q, %q) = %s, want %s", in[0], in[1], got, want)
		}
	}
}
