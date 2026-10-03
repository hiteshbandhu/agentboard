#!/bin/zsh
# Builds release artifacts into dist/:
#   hallmonitor_<v>_<os>_<arch>.tar.gz   CLI for macOS/Linux, amd64/arm64
#   HallMonitor-<v>.zip                  universal menu bar + notch app
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
  d=dist/tmp/hallmonitor_${v}_${os}_${arch}
  mkdir -p $d
  CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build -trimpath -ldflags "$ldflags" -o $d/hallmonitor ./cmd/hallmonitor
  cp LICENSE README.md $d/
  ln -s hallmonitor $d/agentboard  # the old name keeps working
  # No macOS extended attributes in the archive: GNU tar warns about them.
  COPYFILE_DISABLE=1 tar --no-xattrs --no-mac-metadata -C dist/tmp -czf dist/hallmonitor_${v}_${os}_${arch}.tar.gz hallmonitor_${v}_${os}_${arch}
done

# Universal app: both slices of the Swift binary and of the bundled CLI.
app=dist/tmp/HallMonitor.app
mkdir -p $app/Contents/{MacOS,Helpers,Resources}
sed "s|<string>0.1.0</string>|<string>$v</string>|" macos/Info.plist > $app/Contents/Info.plist
cp macos/AppIcon.icns $app/Contents/Resources/
cp -R macos/Fonts $app/Contents/Resources/
for arch in arm64 x86_64; do
  swiftc -O -parse-as-library -target $arch-apple-macos14.0 \
    -framework SwiftUI -framework AppKit -framework UserNotifications \
    macos/Sources/*.swift -o dist/tmp/HallMonitor-$arch
done
lipo -create dist/tmp/HallMonitor-arm64 dist/tmp/HallMonitor-x86_64 -output $app/Contents/MacOS/HallMonitor
lipo -create dist/tmp/hallmonitor_${v}_darwin_arm64/hallmonitor dist/tmp/hallmonitor_${v}_darwin_amd64/hallmonitor \
  -output $app/Contents/Helpers/hallmonitor
ln -s hallmonitor $app/Contents/Helpers/agentboard  # old status lines and scripts
codesign --force --deep -s - $app
(cd dist/tmp && ditto -c -k --keepParent HallMonitor.app ../HallMonitor-$v.zip)

rm -rf dist/tmp
(cd dist && shasum -a 256 *.tar.gz *.zip > checksums.txt)
cat dist/checksums.txt
