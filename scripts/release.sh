#!/bin/zsh
# Builds release artifacts into dist/:
#   agentboard_<v>_<os>_<arch>.tar.gz   CLI for macOS/Linux, amd64/arm64
#   AgentBoard-<v>.zip                  universal menu bar + notch app
#   checksums.txt
#
#   scripts/release.sh 0.1.0
set -euo pipefail
v=${1:?version, e.g. 0.1.0}
root=${0:A:h:h}
cd $root
rm -rf dist && mkdir -p dist/tmp

ldflags="-s -w -X main.version=$v"
for target in darwin/arm64 darwin/amd64 linux/amd64 linux/arm64; do
  os=${target%/*} arch=${target#*/}
  d=dist/tmp/agentboard_${v}_${os}_${arch}
  mkdir -p $d
  CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build -trimpath -ldflags "$ldflags" -o $d/agentboard ./cmd/agentboard
  cp LICENSE README.md $d/
  # No macOS extended attributes in the archive: GNU tar warns about them.
  COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C dist/tmp -czf dist/agentboard_${v}_${os}_${arch}.tar.gz agentboard_${v}_${os}_${arch}
done

# Universal app: both slices of the Swift binary and of the bundled CLI.
app=dist/tmp/AgentBoard.app
mkdir -p $app/Contents/{MacOS,Helpers,Resources}
sed "s|<string>0.1.0</string>|<string>$v</string>|" macos/Info.plist > $app/Contents/Info.plist
for arch in arm64 x86_64; do
  swiftc -O -parse-as-library -target $arch-apple-macos14.0 \
    -framework SwiftUI -framework AppKit -framework UserNotifications \
    macos/Sources/*.swift -o dist/tmp/AgentBoard-$arch
done
lipo -create dist/tmp/AgentBoard-arm64 dist/tmp/AgentBoard-x86_64 -output $app/Contents/MacOS/AgentBoard
lipo -create dist/tmp/agentboard_${v}_darwin_arm64/agentboard dist/tmp/agentboard_${v}_darwin_amd64/agentboard \
  -output $app/Contents/Helpers/agentboard
codesign --force --deep -s - $app
(cd dist/tmp && ditto -c -k --keepParent AgentBoard.app ../AgentBoard-$v.zip)

rm -rf dist/tmp
(cd dist && shasum -a 256 *.tar.gz *.zip > checksums.txt)
cat dist/checksums.txt
