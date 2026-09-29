// Package termimg draws small images inside a Bubble Tea view.
//
// Kitty mode uses the kitty graphics protocol's Unicode placeholders
// (kitty, Ghostty, cmux, WezTerm): the image is uploaded once, then shown by
// writing ordinary text cells, so it survives the renderer redrawing lines.
// Blocks mode works in any truecolor terminal (iTerm2, Terminal.app): each
// cell is "▀" with the top pixel as foreground and the bottom as background.
package termimg

import (
	"bytes"
	"encoding/base64"
	"fmt"
	"image"
	"image/color"
	"image/png"
	"os"
	"strings"

	xdraw "golang.org/x/image/draw"
)

type Mode int

const (
	Off Mode = iota
	Blocks
	Kitty
)

func (m Mode) String() string {
	return [...]string{"off", "blocks", "kitty"}[m]
}

// Detect picks a mode. flag is "auto", "kitty", "blocks" or "off". Auto only
// ever picks kitty or off.
func Detect(flag string) Mode {
	switch flag {
	case "kitty":
		return Kitty
	case "blocks":
		return Blocks
	case "off", "none", "false":
		return Off
	}
	if os.Getenv("TMUX") != "" || strings.HasPrefix(os.Getenv("TERM"), "screen") {
		return Off // placeholders need passthrough setup in tmux
	}
	term := os.Getenv("TERM")
	prog := strings.ToLower(os.Getenv("TERM_PROGRAM"))
	switch {
	case strings.Contains(term, "kitty"), os.Getenv("KITTY_WINDOW_ID") != "",
		strings.Contains(term, "ghostty"), os.Getenv("GHOSTTY_RESOURCES_DIR") != "",
		prog == "ghostty", prog == "wezterm":
		return Kitty
	}
	// Half blocks are too coarse for a logo at card size, so they're opt-in
	// only; other terminals get the text chips.
	return Off
}

// ---- kitty ----

// Transmit returns the escape sequence that uploads img as image id and
// creates a virtual placement of cols×rows cells for placeholders to show.
// q=2 keeps the terminal from replying into our stdin.
func Transmit(id uint32, img image.Image, cols, rows int) string {
	var buf bytes.Buffer
	_ = png.Encode(&buf, img)
	data := base64.StdEncoding.EncodeToString(buf.Bytes())
	var sb strings.Builder
	const chunk = 4096
	for i := 0; i < len(data); i += chunk {
		end := min(i+chunk, len(data))
		more := 0
		if end < len(data) {
			more = 1
		}
		if i == 0 {
			fmt.Fprintf(&sb, "\x1b_Ga=T,U=1,f=100,t=d,q=2,i=%d,c=%d,r=%d,m=%d;%s\x1b\\", id, cols, rows, more, data[i:end])
		} else {
			fmt.Fprintf(&sb, "\x1b_Gm=%d,q=2;%s\x1b\\", more, data[i:end])
		}
	}
	return sb.String()
}

// Cells returns rows lines of cols placeholder cells for image id. The
// image id rides in the foreground color; each cell names its row and column
// with combining diacritics.
func Cells(id uint32, cols, rows int) []string {
	fg := fmt.Sprintf("\x1b[38;2;%d;%d;%dm", (id>>16)&0xff, (id>>8)&0xff, id&0xff)
	out := make([]string, rows)
	for r := 0; r < rows && r < len(diacritics); r++ {
		var sb strings.Builder
		sb.WriteString(fg)
		for c := 0; c < cols && c < len(diacritics); c++ {
			sb.WriteRune(0x10EEEE)
			sb.WriteRune(diacritics[r])
			sb.WriteRune(diacritics[c])
		}
		sb.WriteString("\x1b[39m")
		out[r] = sb.String()
	}
	return out
}

// From kitty's rowcolumn-diacritics.txt; index = row/column number.
var diacritics = []rune{
	0x0305, 0x030D, 0x030E, 0x0310, 0x0312, 0x033D, 0x033E, 0x033F,
	0x0346, 0x034A, 0x034B, 0x034C, 0x0350, 0x0351, 0x0352, 0x0357,
	0x035B, 0x0363, 0x0364, 0x0365, 0x0366, 0x0367, 0x0368, 0x0369,
}

// ---- blocks ----

// HalfBlocks renders img into cols×rows cells, two pixels per cell.
// Transparent pixels keep the terminal's own background.
func HalfBlocks(img image.Image, cols, rows int) []string {
	px := image.NewRGBA(image.Rect(0, 0, cols, rows*2))
	xdraw.CatmullRom.Scale(px, px.Bounds(), img, img.Bounds(), xdraw.Over, nil)
	out := make([]string, rows)
	for r := 0; r < rows; r++ {
		var sb strings.Builder
		for c := 0; c < cols; c++ {
			top, bot := px.RGBAAt(c, r*2), px.RGBAAt(c, r*2+1)
			ts, bs := top.A >= 128, bot.A >= 128
			switch {
			case ts && bs:
				fmt.Fprintf(&sb, "\x1b[38;2;%sm\x1b[48;2;%sm▀\x1b[0m", rgb(top), rgb(bot))
			case ts:
				fmt.Fprintf(&sb, "\x1b[38;2;%sm▀\x1b[0m", rgb(top))
			case bs:
				fmt.Fprintf(&sb, "\x1b[38;2;%sm▄\x1b[0m", rgb(bot))
			default:
				sb.WriteByte(' ')
			}
		}
		out[r] = sb.String()
	}
	return out
}

func rgb(c color.RGBA) string {
	// Undo premultiplication for partially transparent edge pixels.
	if c.A > 0 && c.A < 255 {
		c.R = uint8(min(255, int(c.R)*255/int(c.A)))
		c.G = uint8(min(255, int(c.G)*255/int(c.A)))
		c.B = uint8(min(255, int(c.B)*255/int(c.A)))
	}
	return fmt.Sprintf("%d;%d;%d", c.R, c.G, c.B)
}

// Downscale shrinks img to at most size px square, so uploads stay small.
func Downscale(img image.Image, size int) image.Image {
	if img.Bounds().Dx() <= size {
		return img
	}
	out := image.NewRGBA(image.Rect(0, 0, size, size))
	xdraw.CatmullRom.Scale(out, out.Bounds(), img, img.Bounds(), xdraw.Over, nil)
	return out
}
