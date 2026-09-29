package termimg

import (
	"image"
	"image/color"
	"math/rand/v2"
	"strings"
	"testing"

	"github.com/charmbracelet/lipgloss"
)

func square(n int, c color.RGBA) image.Image {
	img := image.NewRGBA(image.Rect(0, 0, n, n))
	for y := 0; y < n; y++ {
		for x := 0; x < n; x++ {
			img.SetRGBA(x, y, c)
		}
	}
	return img
}

func TestTransmit(t *testing.T) {
	// Big enough to need several chunks.
	img := image.NewRGBA(image.Rect(0, 0, 256, 256))
	r := rand.New(rand.NewPCG(1, 2))
	for i := range img.Pix {
		img.Pix[i] = byte(r.Uint32())
	}
	s := Transmit(0xA1B001, img, 4, 2)
	parts := strings.Split(s, "\x1b\\")
	parts = parts[:len(parts)-1]
	if len(parts) < 2 {
		t.Fatalf("expected chunked upload, got %d part(s)", len(parts))
	}
	first := parts[0]
	for _, want := range []string{"\x1b_Ga=T", "U=1", "f=100", "q=2", "i=10596353", "c=4", "r=2", "m=1;"} {
		if !strings.Contains(first, want) {
			t.Errorf("first chunk missing %q", want)
		}
	}
	for i, p := range parts {
		payload := p[strings.IndexByte(p, ';')+1:]
		if len(payload) > 4096 {
			t.Errorf("chunk %d is %d bytes", i, len(payload))
		}
		last := i == len(parts)-1
		if last != strings.Contains(p, "m=0") {
			t.Errorf("chunk %d: wrong m flag: %q", i, p[:20])
		}
	}
	if lipgloss.Width(s) != 0 {
		t.Errorf("upload should be zero-width, got %d", lipgloss.Width(s))
	}
}

func TestCells(t *testing.T) {
	lines := Cells(0xA1B001, 4, 2)
	if len(lines) != 2 {
		t.Fatalf("%d lines", len(lines))
	}
	for r, l := range lines {
		if w := lipgloss.Width(l); w != 4 {
			t.Errorf("row %d is %d wide", r, w)
		}
		if !strings.HasPrefix(l, "\x1b[38;2;161;176;1m") {
			t.Errorf("row %d: id not in fg color: %q", r, l[:20])
		}
		// Every cell names its row.
		if strings.Count(l, string(rune(0x10EEEE))+string(diacritics[r])) != 4 {
			t.Errorf("row %d: cells don't carry the row diacritic", r)
		}
	}
}

func TestHalfBlocks(t *testing.T) {
	lines := HalfBlocks(square(8, color.RGBA{0xd9, 0x77, 0x57, 0xff}), 4, 2)
	for r, l := range lines {
		if w := lipgloss.Width(l); w != 4 {
			t.Errorf("row %d is %d wide", r, w)
		}
		if !strings.Contains(l, "217;119;87") {
			t.Errorf("row %d lost the color: %q", r, l)
		}
	}
	// Fully transparent image renders as spaces.
	for _, l := range HalfBlocks(image.NewRGBA(image.Rect(0, 0, 8, 8)), 4, 2) {
		if l != "    " {
			t.Errorf("transparent row = %q", l)
		}
	}
}
