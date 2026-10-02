package claude

import (
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestReadSubagents(t *testing.T) {
	dir := t.TempDir()
	parent := filepath.Join(dir, "s1.jsonl")
	sub := filepath.Join(dir, "s1", "subagents")
	if err := os.MkdirAll(sub, 0o755); err != nil {
		t.Fatal(err)
	}
	write := func(name, s string) {
		if err := os.WriteFile(filepath.Join(sub, name), []byte(s), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	// a: foreground, finished. b: foreground, running. c: background,
	// launched (its tool result came back) but not finished. d: background,
	// finished.
	for _, a := range []struct{ id, tool, shape, desc string }{
		{"a", "toolu_A", "foreground", "Read the docs"},
		{"b", "toolu_B", "foreground", "Map the codebase"},
		{"c", "toolu_C", "background", "Research launches"},
		{"d", "toolu_D", "background", "Check the build"},
	} {
		write("agent-"+a.id+".meta.json", `{"description":"`+a.desc+`","toolUseId":"`+a.tool+`","requestShape":"`+a.shape+`"}`)
		write("agent-"+a.id+".jsonl", "{}\n")
	}
	os.WriteFile(parent, []byte(`{"type":"user","message":{"content":[{"tool_use_id":"toolu_A","type":"tool_result"}]}}
{"type":"user","message":{"content":[{"tool_use_id":"toolu_C","type":"tool_result","content":"Async agent launched"}]}}
{"type":"user","message":{"content":[{"tool_use_id":"toolu_D","type":"tool_result","content":"Async agent launched"}]}}
{"type":"user","message":{"content":"<task-notification>\n<tool-use-id>toolu_D</tool-use-id>\n</task-notification>"}}
`), 0o644)

	sa := readSubagents(parent, time.Now())
	if sa == nil || sa.Total != 4 || sa.Running != 2 {
		t.Fatalf("got %+v, want 2 of 4 running", sa)
	}
	if len(sa.Active) != 2 {
		t.Errorf("active = %v", sa.Active)
	}

	// B's result arrives: picked up from the appended part only.
	f, _ := os.OpenFile(parent, os.O_APPEND|os.O_WRONLY, 0)
	f.WriteString(`{"type":"user","message":{"content":[{"tool_use_id":"toolu_B","type":"tool_result"}]}}` + "\n")
	f.Close()
	if sa := readSubagents(parent, time.Now()); sa.Running != 1 || sa.Active[0] != "Research launches" {
		t.Errorf("after B finished: %+v", sa)
	}

	// Long silent and never heard back from: gone.
	if sa := readSubagents(parent, time.Now().Add(time.Hour)); sa.Running != 0 {
		t.Errorf("silent subagents still running: %+v", sa)
	}
}
