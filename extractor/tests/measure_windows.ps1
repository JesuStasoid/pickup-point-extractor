<#
  Resource measurements for the built exe(s).
  .\tests\measure_windows.ps1 -Exe <onefile.exe> [-OneDirExe <onedir.exe>] -DemoFile <sample.pdf> [-Shot <png>]
  - CLI startup: --version-json, process start -> exit (no window), N runs
  - GUI: start -> window visible, idle RAM / CPU over 10 s, then closed via WM_CLOSE
  - Demo: GUI extracts DemoFile once; peak working set; optional window screenshot
#>
param([Parameter(Mandatory)][string]$Exe, [string]$OneDirExe, [Parameter(Mandatory)][string]$DemoFile,
      [string]$Shot, [int]$Runs = 7)
$ErrorActionPreference = "Stop"
$Title = "Pick-up point extractor v1.0"
Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public static class W {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc f, IntPtr l);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static IntPtr Find(string title, out uint pid) {
    IntPtr found = IntPtr.Zero; uint p = 0;
    EnumWindows((h, l) => { var sb = new StringBuilder(256); GetWindowText(h, sb, 256);
      if (sb.ToString() == title && IsWindowVisible(h)) { found = h; GetWindowThreadProcessId(h, out p); return false; } return true; }, IntPtr.Zero);
    pid = p; return found;
  }
}
"@
Add-Type -AssemblyName System.Drawing
function Median($a) { $s = $a | Sort-Object; $s[[int][Math]::Floor($s.Count / 2)] }
function TreeProcs($root) {
  @($root) + @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($root.Id)" | ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue })
}
function CliStartup($exe) {
  $j = Join-Path $env:TEMP "ppe_ver.json"; $t = @()
  for ($i = 0; $i -lt $Runs; $i++) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = [Diagnostics.Process]::Start($exe, "--version-json `"$j`""); $p.WaitForExit(); $sw.Stop()
    $t += $sw.ElapsedMilliseconds
  }
  [pscustomobject]@{ first_ms = $t[0]; median_ms = (Median $t[1..($t.Count-1)]); all = ($t -join ",") }
}
function Gui($exe, $args2, [switch]$Idle, [string]$ShotPath) {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $p = [Diagnostics.Process]::Start($exe, $args2)
  $h = [IntPtr]::Zero; $wpid = 0
  while ($sw.ElapsedMilliseconds -lt 20000) { $h = [W]::Find($Title, [ref]$wpid); if ($h -ne [IntPtr]::Zero) { break }; Start-Sleep -Milliseconds 10 }
  $visible = $sw.ElapsedMilliseconds
  $o = [ordered]@{ window_ms = $visible }
  $procs = TreeProcs $p
  if ($Idle) {
    Start-Sleep 3
    $procs | ForEach-Object { $_.Refresh() }
    $c0 = ($procs | ForEach-Object { $_.TotalProcessorTime.TotalMilliseconds } | Measure-Object -Sum).Sum
    Start-Sleep 10
    $procs | ForEach-Object { $_.Refresh() }
    $c1 = ($procs | ForEach-Object { $_.TotalProcessorTime.TotalMilliseconds } | Measure-Object -Sum).Sum
    $o.idle_cpu_ms_per_10s = [Math]::Round($c1 - $c0, 1)
  } else { Start-Sleep 2; $procs | ForEach-Object { $_.Refresh() } }
  $o.procs = ($procs | ForEach-Object { "{0}: WS {1:N1} MB, private {2:N1} MB, peak WS {3:N1} MB" -f $_.Id, ($_.WorkingSet64/1MB), ($_.PrivateMemorySize64/1MB), ($_.PeakWorkingSet64/1MB) }) -join " | "
  $o.total_ws_mb = [Math]::Round((($procs | Measure-Object WorkingSet64 -Sum).Sum)/1MB, 1)
  $o.total_private_mb = [Math]::Round((($procs | Measure-Object PrivateMemorySize64 -Sum).Sum)/1MB, 1)
  $o.gui_peak_ws_mb = [Math]::Round(((Get-Process -Id $wpid).PeakWorkingSet64)/1MB, 1)
  if ($ShotPath) {
    $r = New-Object W+RECT; [void][W]::GetWindowRect($h, [ref]$r)
    $bmp = New-Object Drawing.Bitmap ($r.R - $r.L), ($r.B - $r.T); $g = [Drawing.Graphics]::FromImage($bmp)
    $dc = $g.GetHdc(); [void][W]::PrintWindow($h, $dc, 2); $g.ReleaseHdc($dc); $bmp.Save($ShotPath); $g.Dispose(); $bmp.Dispose()
    $o.shot = $ShotPath
  }
  [void][W]::PostMessage($h, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)   # WM_CLOSE
  if (-not $p.WaitForExit(10000)) { $p.Kill(); $o.closed = "killed" } else { $o.closed = "WM_CLOSE ok" }
  [pscustomobject]$o
}

"exe size: {0:N1} MB" -f ((Get-Item $Exe).Length / 1MB)
"--- CLI startup (start -> exit, no window), onefile"; CliStartup $Exe | Format-List | Out-String
if ($OneDirExe) { "--- CLI startup, onedir"; CliStartup $OneDirExe | Format-List | Out-String }
"--- GUI onefile: idle"; Gui $Exe "" -Idle | Format-List | Out-String
"--- GUI onefile: window time, 2 more runs"; 1..2 | ForEach-Object { (Gui $Exe "").window_ms }
if ($OneDirExe) { "--- GUI onedir: idle"; Gui $OneDirExe "" -Idle | Format-List | Out-String
                  "--- GUI onedir: window time, 2 more runs"; 1..2 | ForEach-Object { (Gui $OneDirExe "").window_ms } }
"--- GUI onefile: demo extraction of $(Split-Path $DemoFile -Leaf)"; Gui $Exe "--demo `"$DemoFile`"" -ShotPath $Shot | Format-List | Out-String
