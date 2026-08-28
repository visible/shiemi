<#
.SYNOPSIS
Press a native control by its accessible name, so menus and bubbles can be
opened for a screenshot.

.DESCRIPTION
The toolbar and the menus are Views, not windows, so there is nothing for a
click to address and nothing PrintWindow can reach until the surface is open.
Synthetic keystrokes were the other option and they need the window in the
foreground, which loses whatever the user was doing.

UI Automation needs neither: Invoke works on a background window. Chromium
builds its accessibility tree lazily on the first query, so the tree is retried
rather than trusted the first time.

.EXAMPLE
powershell -File utils/invoke_ui.ps1 -Id 1234 -List

.EXAMPLE
powershell -File utils/invoke_ui.ps1 -Id 1234 -Name 'Customise and control'
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][int]$Id,
  [string]$Name,
  [ValidateSet('Button', 'MenuItem', 'Any')][string]$Role = 'Button',
  [switch]$List,
  [switch]$Click,
  [int]$TimeoutSeconds = 20
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes

Add-Type -Namespace Native -Name Mouse -MemberDefinition @'
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(
      uint flags, uint x, uint y, uint data, IntPtr extra);
'@

$A = [System.Windows.Automation.AutomationElement]
$Condition = [System.Windows.Automation.PropertyCondition]
$Scope = [System.Windows.Automation.TreeScope]::Descendants

function Get-BrowserWindow([int]$processId) {
  $byPid = New-Object $Condition ($A::ProcessIdProperty, $processId)
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $windows = $A::RootElement.FindAll(
      [System.Windows.Automation.TreeScope]::Children, $byPid)
    foreach ($w in $windows) {
      if ($w.Current.ControlType.ProgrammaticName -eq 'ControlType.Window') {
        return $w
      }
    }
    Start-Sleep -Milliseconds 200
  }
  throw "no window for process $processId"
}

function Get-Controls($window) {
  if ($Role -eq 'Any') {
    return $window.FindAll($Scope, [System.Windows.Automation.Condition]::TrueCondition)
  }
  $type = [System.Windows.Automation.ControlType]::$Role
  return $window.FindAll($Scope, (New-Object $Condition ($A::ControlTypeProperty, $type)))
}

$window = Get-BrowserWindow $Id

# The tree is empty until accessibility spins up, and the count grows for a
# moment after that, so wait for it to settle rather than for a fixed delay.
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$previous = -1
while ((Get-Date) -lt $deadline) {
  $controls = Get-Controls $window
  if ($controls.Count -gt 0 -and $controls.Count -eq $previous) { break }
  $previous = $controls.Count
  Start-Sleep -Milliseconds 300
}

if ($List) {
  foreach ($c in $controls) {
    $n = $c.Current.Name
    if ($n) { "{0,-22} {1}" -f $c.Current.ControlType.ProgrammaticName.Replace('ControlType.', ''), $n }
  }
  exit 0
}

if (-not $Name) { throw 'pass -Name or -List' }

foreach ($c in $controls) {
  if ($c.Current.Name -notlike "*$Name*") { continue }

  # Chromium advertises ExpandCollapse on its menu buttons but faults when it
  # is called, so a real click is the only way into the menus. That needs the
  # window raised, which is why it is opt-in rather than a silent fallback.
  if ($Click) {
    [Native.Mouse]::SetForegroundWindow(
      [IntPtr]$window.Current.NativeWindowHandle) | Out-Null
    Start-Sleep -Milliseconds 400

    # Raising the window rebuilds the tree, which leaves the match above stale:
    # a stale element reports an empty rectangle, and clicking that lands at the
    # screen corner on whatever happens to be there. Re-resolve and check the
    # rectangle is real and inside the window before pressing anything.
    $fresh = Get-Controls $window | Where-Object { $_.Current.Name -eq $Name }
    if (-not $fresh) {
      throw "'$Name' is gone after raising the window; -Click needs an exact name"
    }
    $c = @($fresh)[0]
    $r = $c.Current.BoundingRectangle
    $w = $window.Current.BoundingRectangle
    if ($r.Width -le 0 -or $r.Height -le 0 -or -not $w.Contains($r)) {
      throw "'$Name' has no usable rectangle ($r) inside the window ($w)"
    }

    [Native.Mouse]::SetCursorPos(
      [int]($r.X + $r.Width / 2), [int]($r.Y + $r.Height / 2)) | Out-Null
    Start-Sleep -Milliseconds 150
    [Native.Mouse]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
    [Native.Mouse]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
    "clicked: $($c.Current.Name)"
    exit 0
  }

  # A button that opens a menu is expandable rather than invokable, and the
  # toolbar has both kinds.
  $invoke = [System.Windows.Automation.InvokePattern]::Pattern
  $expand = [System.Windows.Automation.ExpandCollapsePattern]::Pattern
  $supported = $c.GetSupportedPatterns()

  if ($supported -contains $invoke) {
    $c.GetCurrentPattern($invoke).Invoke()
  } elseif ($supported -contains $expand) {
    $c.GetCurrentPattern($expand).Expand()
  } else {
    throw "'$($c.Current.Name)' supports neither Invoke nor ExpandCollapse"
  }

  "pressed: $($c.Current.Name)"
  exit 0
}

throw "no $Role matching '$Name'; run with -List to see what is there"
