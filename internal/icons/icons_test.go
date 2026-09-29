package icons

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

// Writes what each source produces to $ICON_OUT for eyeballing; skips the
// network part unless ICON_NET=1.
func TestSources(t *testing.T) {
	out := os.Getenv("ICON_OUT")
	for name, sp := range specs {
		if img, err := fromApps(sp.apps); err == nil {
			t.Logf("%s: app icon %v", name, img.Bounds())
			if out != "" {
				_ = writePNG(filepath.Join(out, name+"-app.png"), img)
			}
		} else {
			t.Logf("%s: no app icon (%v)", name, err)
		}
		if sp.slug == "" {
			img, err := tile([]byte(sp.svg), sp.tile, sp.fg, 256)
			if err != nil {
				t.Errorf("%s: builtin: %v", name, err)
			} else if out != "" {
				_ = writePNG(filepath.Join(out, name+"-builtin.png"), img)
			}
			continue
		}
		if os.Getenv("ICON_NET") != "1" {
			continue
		}
		img, err := fromCDN(context.Background(), sp)
		if err != nil {
			t.Errorf("%s: cdn: %v", name, err)
			continue
		}
		t.Logf("%s: cdn icon %v", name, img.Bounds())
		if out != "" {
			_ = writePNG(filepath.Join(out, name+"-cdn.png"), img)
		}
	}
}
