package claude

import (
	"bytes"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/hiteshbandhu/agentboard/internal/model"
)

// Claude Code keeps each subagent's transcript next to its parent's, in
// <session>/subagents/agent-<id>.jsonl, with a .meta.json saying what it is
// and which Agent tool call started it. A subagent is running until its parent
// hears back: the tool result for a foreground one, a <task-notification> for
// a background one (whose tool result only says it launched).

type subagentMeta struct {
	Description  string `json:"description"`
	ToolUseID    string `json:"toolUseId"`
	RequestShape string `json:"requestShape"`
}

// finishLog remembers which Agent calls a parent transcript has heard back
// from, reading only what was appended since last time.
type finishLog struct {
	offset   int64
	results  map[string]bool // tool results seen
	notified map[string]bool // task notifications seen
}

var (
	finishMu   sync.Mutex
	finishLogs = map[string]*finishLog{}

	resultRe   = regexp.MustCompile(`"tool_use_id":"(toolu_[A-Za-z0-9_]+)"`)
	notifiedRe = regexp.MustCompile(`<tool-use-id>(toolu_[A-Za-z0-9_]+)</tool-use-id>`)
)

// A subagent nobody heard back from that has also been silent this long is
// taken as gone (the session was killed mid-run, say).
const subagentSilence = 30 * time.Minute

func readSubagents(transcript string, now time.Time) *model.Subagents {
	dir := strings.TrimSuffix(transcript, ".jsonl") + string(filepath.Separator) + "subagents"
	metas, _ := filepath.Glob(filepath.Join(dir, "agent-*.meta.json"))
	if len(metas) == 0 {
		return nil
	}
	finishMu.Lock()
	defer finishMu.Unlock()
	fl := finishLogs[transcript]
	if fl == nil {
		fl = &finishLog{results: map[string]bool{}, notified: map[string]bool{}}
		finishLogs[transcript] = fl
	}
	fl.update(transcript)

	type running struct {
		desc string
		at   time.Time
	}
	var live []running
	sa := &model.Subagents{Total: len(metas)}
	for _, mp := range metas {
		b, err := os.ReadFile(mp)
		if err != nil {
			continue
		}
		var m subagentMeta
		if json.Unmarshal(b, &m) != nil || m.ToolUseID == "" {
			continue
		}
		done := fl.results[m.ToolUseID]
		if m.RequestShape == "background" {
			done = fl.notified[m.ToolUseID]
		}
		if done {
			continue
		}
		st, err := os.Stat(strings.TrimSuffix(mp, ".meta.json") + ".jsonl")
		if err != nil || now.Sub(st.ModTime()) > subagentSilence {
			continue
		}
		live = append(live, running{m.Description, st.ModTime()})
	}
	sort.Slice(live, func(i, j int) bool { return live[i].at.After(live[j].at) })
	sa.Running = len(live)
	for _, r := range live {
		if len(sa.Active) == 3 {
			break
		}
		if r.desc != "" {
			sa.Active = append(sa.Active, model.Snip(r.desc, 60))
		}
	}
	return sa
}

func (fl *finishLog) update(path string) {
	f, err := os.Open(path)
	if err != nil {
		return
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return
	}
	if st.Size() < fl.offset { // rewritten
		fl.offset = 0
	}
	const chunk = 16 << 20
	for fl.offset < st.Size() {
		n := min(st.Size()-fl.offset, chunk)
		buf := make([]byte, n)
		if _, err := f.ReadAt(buf, fl.offset); err != nil && err != io.EOF {
			return
		}
		end := bytes.LastIndexByte(buf, '\n')
		if end < 0 {
			if n == chunk {
				fl.offset += n // one enormous line; nothing we need is in it
				continue
			}
			return // a line still being written
		}
		buf = buf[:end+1]
		for _, m := range resultRe.FindAllSubmatch(buf, -1) {
			fl.results[string(m[1])] = true
		}
		for _, m := range notifiedRe.FindAllSubmatch(buf, -1) {
			fl.notified[string(m[1])] = true
		}
		fl.offset += int64(end + 1)
	}
}
