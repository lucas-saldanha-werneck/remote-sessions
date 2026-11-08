// ax-press: find a UI element of a running app by role and title prefix through the macOS
// Accessibility API, print it, and optionally press it. Used by claude-desk to flip the
// "Remote Control" switch of a Claude desktop app session.
//
// usage: ax-press <pid> <role> <title-prefix> [press]
// exit 2 = element not found. Build: swiftc -O -o ax-press ax-press.swift
import Cocoa

let a = CommandLine.arguments
guard a.count >= 4, let pid = pid_t(a[1]) else {
  print("usage: ax-press <pid> <role> <title-prefix> [press]")
  exit(1)
}
let app = AXUIElementCreateApplication(pid)
// Electron apps only build their accessibility tree when asked to
AXUIElementSetAttributeValue(app, "AXManualAccessibility" as CFString, kCFBooleanTrue)
Thread.sleep(forTimeInterval: 1.0)

func attr(_ e: AXUIElement, _ n: String) -> AnyObject? {
  var v: AnyObject?
  AXUIElementCopyAttributeValue(e, n as CFString, &v)
  return v
}

var found: AXUIElement? = nil
func walk(_ e: AXUIElement, _ d: Int) {
  if found != nil || d > 45 { return }
  if (attr(e, "AXRole") as? String) == a[2], let t = attr(e, "AXTitle") as? String, t.hasPrefix(a[3]) {
    found = e
    return
  }
  for k in (attr(e, "AXChildren") as? [AXUIElement]) ?? [] { walk(k, d + 1) }
}
walk(app, 0)

guard let f = found else { print("NOT FOUND"); exit(2) }
print("found:", attr(f, "AXTitle") as? String ?? "", "value:", attr(f, "AXValue") ?? "nil" as AnyObject)
if a.count > 4 {
  let r = AXUIElementPerformAction(f, "AXPress" as CFString)
  print("press result:", r.rawValue)
  Thread.sleep(forTimeInterval: 2)
  print("value now:", attr(f, "AXValue") ?? "nil" as AnyObject)
}
