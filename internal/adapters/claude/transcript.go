package claude

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/hiteshbandhu/hallmonitor/internal/model"
)

// activity is what we pull from the tail of a session transcript: the latest
// tool call or reply, the latest real user prompt, model and context size.
// Tool inputs are reduced to a short hint (a file name, a description); full
// transcripts never leave this function.
type activity struct {
	Last     string
	LastAt   time.Time
	Prompt   string
	Model    string
	Context  int
	Activity []int64
}

var nonAlnum = regexp.MustCompile(`[^A-Za-z0-9]`)

func transcriptPath(home, cwd, sessionID string) string {
	if sessionID == "" {
		return ""
	}
	p := filepath.Join(home, ".claude", "projects", nonAlnum.ReplaceAllString(cwd, "-"), sessionID+".jsonl")
	if _, err := os.Stat(p); err == nil {
		return p
	}
	m, _ := filepath.Glob(filepath.Join(home, ".claude", "projects", "*", sessionID+".jsonl"))
	if len(m) > 0 {
		return m[0]
	}
	return ""
}

type tLine struct {
	Type      string `json:"type"`
	Timestamp string `json:"timestamp"`
	IsMeta    bool   `json:"isMeta"`
	Message   struct {
		Model   string          `json:"model"`
		Content json.RawMessage `json:"content"`
		Usage   *struct {
			Input       int `json:"input_tokens"`
			CacheRead   int `json:"cache_read_input_tokens"`
			CacheCreate int `json:"cache_creation_input_tokens"`
		} `json:"usage"`
	} `json:"message"`
}

type tBlock struct {
	Type  string          `json:"type"`
	Name  string          `json:"name"`
	Text  string          `json:"text"`
	Input json.RawMessage `json:"input"`
}

func readActivity(path string) (activity, error) {
	var a activity
	f, err := os.Open(path)
	if err != nil {
		return a, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return a, err
	}
	const tail = 192 * 1024
	off := max(st.Size()-tail, 0)
	buf := make([]byte, st.Size()-off)
	if _, err := f.ReadAt(buf, off); err != nil && err != io.EOF {
		return a, err
	}
	lines := strings.Split(string(buf), "\n")
	if off > 0 && len(lines) > 0 {
		lines = lines[1:]
	}
	now := time.Now()
	for _, l := range lines {
		if l == "" {
			continue
		}
		var tl tLine
		if json.Unmarshal([]byte(l), &tl) != nil {
			continue
		}
		ts, _ := time.Parse(time.RFC3339Nano, tl.Timestamp)
		switch tl.Type {
		case "user":
			if tl.IsMeta {
				continue
			}
			var s string
			if json.Unmarshal(tl.Message.Content, &s) == nil && isHumanPrompt(s) {
				a.Prompt = model.Snip(s, 120)
			}
		case "assistant":
			if tl.Message.Model != "" && !strings.HasPrefix(tl.Message.Model, "<") {
				a.Model = tl.Message.Model
			}
			if u := tl.Message.Usage; u != nil {
				if c := u.Input + u.CacheRead + u.CacheCreate; c > 0 {
					a.Context = c
				}
			}
			var blocks []tBlock
			if json.Unmarshal(tl.Message.Content, &blocks) != nil {
				continue
			}
			for _, b := range blocks {
				switch b.Type {
				case "tool_use":
					a.Last = toolLine(b.Name, b.Input)
					a.LastAt = ts
				case "text":
					if t := strings.TrimSpace(b.Text); t != "" {
						a.Last = "↳ " + model.Snip(t, 100)
						a.LastAt = ts
					}
				}
			}
		}
	}
	a.Activity = scanActivity(f, st.Size(), now)
	return a, nil
}

// scanActivity pulls event timestamps from a larger tail without decoding
// each line: transcript lines can be megabytes (screenshots, big outputs), so
// the 192KB window above may only span a minute.
func scanActivity(f *os.File, size int64, now time.Time) []int64 {
	const tail = 4 << 20
	off := max(size-tail, 0)
	buf := make([]byte, size-off)
	if _, err := f.ReadAt(buf, off); err != nil && err != io.EOF {
		return nil
	}
	key := []byte(`"timestamp":"`)
	var out []int64
	for _, line := range bytes.Split(buf, []byte("\n")) {
		if !bytes.Contains(line, []byte(`"role":"assistant"`)) && !bytes.Contains(line, []byte(`"role":"user"`)) {
			continue
		}
		i := bytes.LastIndex(line, key)
		if i < 0 || i+len(key)+20 > len(line) {
			continue
		}
		rest := line[i+len(key):]
		j := bytes.IndexByte(rest, '"')
		if j < 0 {
			continue
		}
		ts, err := time.Parse(time.RFC3339Nano, string(rest[:j]))
		if err != nil {
			continue
		}
		out = model.AddActivity(out, ts, now)
	}
	return out
}

// isHumanPrompt filters out command wrappers and system-injected turns.
func isHumanPrompt(s string) bool {
	s = strings.TrimSpace(s)
	return s != "" && !strings.HasPrefix(s, "<") && !strings.HasPrefix(s, "Caveat:")
}

// toolLine turns a tool call into "Name · hint" without dumping inputs.
func toolLine(name string, input json.RawMessage) string {
	var in map[string]any
	_ = json.Unmarshal(input, &in)
	str := func(k string) string {
		v, _ := in[k].(string)
		return v
	}
	short := name
	if strings.HasPrefix(name, "mcp__") {
		parts := strings.Split(name, "__")
		short = parts[len(parts)-1]
	}
	hint := ""
	switch {
	case str("description") != "":
		hint = str("description")
	case str("file_path") != "":
		hint = filepath.Base(str("file_path"))
	case str("path") != "":
		hint = filepath.Base(str("path"))
	case str("pattern") != "":
		hint = str("pattern")
	case str("url") != "":
		hint = str("url")
	case str("query") != "":
		hint = str("query")
	case str("prompt") != "":
		hint = str("prompt")
	}
	if hint == "" {
		return short
	}
	return short + " · " + model.Snip(hint, 70)
}
