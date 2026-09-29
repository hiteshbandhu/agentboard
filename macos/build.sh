#!/bin/zsh
# Builds AgentBoard.app (menu bar + notch) with the Command Line Tools; no
# Xcode project needed. The agentboard CLI is bundled in Contents/Helpers so
# the app works on its own.
#
#   macos/build.sh            # -> macos/build/AgentBoard.app
#   macos/build.sh --install  # also copy to ~/Applications and launch
set -euo pipefail
cd "${0:A:h}"
root=${0:A:h:h}
out=build/AgentBoard.app

rm -rf build && mkdir -p "$out/Contents/MacOS" "$out/Contents/Helpers" "$out/Contents/Resources"
cp Info.plist "$out/Contents/Info.plist"

swiftc -O -parse-as-library -target arm64-apple-macos14.0 \
  -framework SwiftUI -framework AppKit -framework UserNotifications \
  Sources/*.swift -o "$out/Contents/MacOS/AgentBoard"

(cd "$root" && go build -o "macos/$out/Contents/Helpers/agentboard" ./cmd/agentboard)

codesign --force --deep -s - "$out" >/dev/null
echo "built $out"

if [[ ${1:-} == --install ]]; then
  pkill -x AgentBoard 2>/dev/null || true
  mkdir -p ~/Applications
  rm -rf ~/Applications/AgentBoard.app
  cp -R "$out" ~/Applications/
  open ~/Applications/AgentBoard.app
  echo "installed ~/Applications/AgentBoard.app"
fi
