package usage

import (
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Named is a labeled total, for top-N lists.
type Named struct {
	Name     string   `json:"name"`
	Provider string   `json:"provider,omitempty"`
	Counters Counters `json:"counters"`
}

// DayTotal is one day, split by provider.
type DayTotal struct {
	Date       string              `json:"date"`
	ByProvider map[string]Counters `json:"by_provider"`
}

// Summary covers the days in [From, To].
type Summary struct {
	From, To   string              `json:"-"`
	Total      Counters            `json:"total"`
	ByProvider map[string]Counters `json:"by_provider"`
	Sessions   int                 `json:"sessions"`
	Days       []DayTotal          `json:"days"`
	// Heat[weekday][hour] = active seconds (weekday 0 = Monday).
	Heat       [7][24]float64       `json:"heat"`
	Projects   []Named              `json:"projects"`
	Models     []Named              `json:"models"`
	Tools      []Named              `json:"tools"`
	RateLimits map[string]RateLimit `json:"rate_limits,omitempty"`
}

// Summarize reads the ledger for the last n days, today included. It only
// reads; call Update first for fresh numbers.
func (l *Ledger) Summarize(n int) Summary {
	now := time.Now()
	s := Summary{ByProvider: map[string]Counters{}}
	projects, models, tools := map[string]*Named{}, map[string]*Named{}, map[string]*Named{}
	sessions := map[string]bool{}
	for i := n - 1; i >= 0; i-- {
		date := now.AddDate(0, 0, -i).Format("2006-01-02")
		if s.From == "" {
			s.From = date
		}
		s.To = date
		dt := DayTotal{Date: date, ByProvider: map[string]Counters{}}
		d := readDay(filepath.Join(l.Dir, "days", date+".json"))
		if d == nil {
			s.Days = append(s.Days, dt)
			continue
		}
		day, _ := time.ParseInLocation("2006-01-02", date, time.Local)
		wd := (int(day.Weekday()) + 6) % 7
		for key, c := range d.Buckets {
			parts := strings.SplitN(key, "|", 4)
			if len(parts) != 4 {
				continue
			}
			hour, _ := strconv.Atoi(parts[0])
			prov, proj, model := parts[1], parts[2], parts[3]
			s.Total.Add(*c)
			pc := s.ByProvider[prov]
			pc.Add(*c)
			s.ByProvider[prov] = pc
			dc := dt.ByProvider[prov]
			dc.Add(*c)
			dt.ByProvider[prov] = dc
			if hour >= 0 && hour < 24 {
				s.Heat[wd][hour] += c.Active
			}
			bump(projects, proj, "", *c)
			if model != "" {
				bump(models, model, prov, *c)
			}
		}
		for key, calls := range d.Tools {
			prov, name, _ := strings.Cut(key, "|")
			bump(tools, name, prov, Counters{Tools: calls})
		}
		for id := range d.Sessions {
			sessions[id] = true
		}
		s.Days = append(s.Days, dt)
	}
	s.Sessions = len(sessions)
	s.Projects = top(projects, func(c Counters) float64 { return c.Active })
	s.Models = top(models, func(c Counters) float64 { return float64(c.Tokens.Total()) })
	s.Tools = top(tools, func(c Counters) float64 { return float64(c.Tools) })
	s.RateLimits = l.rateLimits()
	return s
}

func (l *Ledger) rateLimits() map[string]RateLimit {
	st := &state{}
	if b, err := os.ReadFile(filepath.Join(l.Dir, "state.json")); err == nil {
		_ = jsonUnmarshal(b, st)
	}
	out := map[string]RateLimit{}
	for k, v := range st.RateLimits {
		out[k] = v
	}
	for k, v := range l.claudeLimits() {
		out[k] = v
	}
	return out
}

func bump(m map[string]*Named, name, prov string, c Counters) {
	k := prov + "|" + name
	n := m[k]
	if n == nil {
		n = &Named{Name: name, Provider: prov}
		m[k] = n
	}
	n.Counters.Add(c)
}

func top(m map[string]*Named, by func(Counters) float64) []Named {
	out := make([]Named, 0, len(m))
	for _, n := range m {
		out = append(out, *n)
	}
	sort.Slice(out, func(i, j int) bool {
		a, b := by(out[i].Counters), by(out[j].Counters)
		if a != b {
			return a > b
		}
		return out[i].Name < out[j].Name
	})
	return out
}
