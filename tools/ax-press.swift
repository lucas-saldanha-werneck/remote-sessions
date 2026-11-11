// ax-press: find a UI element of a running app by role and title prefix through the macOS
// Accessibility API, print it, and optionally act on it. Used by claude-desk to drive a Claude desktop
// app session: the "Remote Control" switch, the permission mode menu and the prompt box.
//
// usage: ax-press <pid> <role> <title-prefix>[|<other prefix>...] [press | set <text> | pick <item prefix>]
//   a prefix ending in $ must match the whole title
//   press        press the element
//   set <text>   focus the element and set its value (a text box); prints the value read back
//   pick <item>  press the element (a pop-up button), then press the menu item whose title starts with <item>
// exit 2 = element (or menu item) not found, 3 = the value read back differs. Build: swiftc -O -o ax-press ax-press.swift
import Cocoa

let a = CommandLine.arguments
guard a.count >= 4, let pid = pid_t(a[1]) else {
  print("usage: ax-press <pid> <role> <title-prefix>[|<prefix>...] [press | set <text> | pick <item prefix>]")
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

func find(_ role: String, _ prefixes: [String]) -> AXUIElement? {
  var found: AXUIElement? = nil
  func walk(_ e: AXUIElement, _ d: Int) {
    if found != nil || d > 60 { return }
    if (attr(e, "AXRole") as? String) == role, let t = attr(e, "AXTitle") as? String,
       prefixes.contains(where: { $0.hasSuffix("$") ? t == String($0.dropLast()) : t.hasPrefix($0) }) {
      found = e
      return
    }
    for k in (attr(e, "AXChildren") as? [AXUIElement]) ?? [] { walk(k, d + 1) }
  }
  walk(app, 0)
  return found
}

guard let f = find(a[2], a[3].components(separatedBy: "|")) else { print("NOT FOUND"); exit(2) }
print("found:", attr(f, "AXTitle") as? String ?? "", "value:", attr(f, "AXValue") ?? "nil" as AnyObject)
let action = a.count > 4 ? a[4] : ""
switch action {
case "":
  break
case "set":
  let text = a.count > 5 ? a[5] : ""
  AXUIElementSetAttributeValue(f, "AXFocused" as CFString, kCFBooleanTrue)
  let r = AXUIElementSetAttributeValue(f, "AXValue" as CFString, text as CFString)
  print("set result:", r.rawValue)
  Thread.sleep(forTimeInterval: 0.8)
  let now = attr(f, "AXValue") as? String ?? ""
  print("value now:", now)
  if now != text { exit(3) }
case "pick":
  let item = a.count > 5 ? a[5] : ""
  print("press result:", AXUIElementPerformAction(f, "AXPress" as CFString).rawValue)
  Thread.sleep(forTimeInterval: 1.0)
  guard let m = find("AXMenuItem", [item]) else {
    // close the menu again: Escape to the app
    for down in [true, false] { CGEvent(keyboardEventSource: nil, virtualKey: 53, keyDown: down)?.postToPid(pid) }
    print("MENU ITEM NOT FOUND:", item)
    exit(2)
  }
  print("picked:", attr(m, "AXTitle") as? String ?? "", "result:", AXUIElementPerformAction(m, "AXPress" as CFString).rawValue)
  Thread.sleep(forTimeInterval: 1.0)
default:  // "press" (and any other word, as before)
  let r = AXUIElementPerformAction(f, "AXPress" as CFString)
  print("press result:", r.rawValue)
  Thread.sleep(forTimeInterval: 2)
  print("value now:", attr(f, "AXValue") ?? "nil" as AnyObject)
}
