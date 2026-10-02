package focus

import "testing"

func TestAppOf(t *testing.T) {
	for in, want := range map[string]string{
		"/System/Applications/Utilities/Terminal.app/Contents/MacOS/Terminal":                                          "/System/Applications/Utilities/Terminal.app",
		"/Applications/Visual Studio Code.app/Contents/Frameworks/Code Helper (Plugin).app/Contents/MacOS/Code Helper": "/Applications/Visual Studio Code.app",
		"-zsh":  "",
		"login": "",
	} {
		if got := appOf(in); got != want {
			t.Errorf("appOf(%q) = %q, want %q", in, got, want)
		}
	}
}
