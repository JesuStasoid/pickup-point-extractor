<#
  Runs the built exe (hidden --cli mode, no window) on copies of the sample files
  in a temp folder, compares the CSVs byte-for-byte with reference CSVs and
  checks that broken inputs fail cleanly.

  .\tests\test_frozen_windows.ps1 -Exe "...\Pick-up point extractor v1.0.exe" `
      -Sample "a.dbpr=ref_a.csv","b.pdf=ref_b.csv"
#>
param(
    [Parameter(Mandatory)][string]$Exe,
    [Parameter(Mandatory)][string[]]$Sample
)
$ErrorActionPreference = "Stop"
$T = Join-Path $env:TEMP "ppe_frozen_test"
Remove-Item -Recurse -Force $T -ErrorAction SilentlyContinue
New-Item -ItemType Directory $T | Out-Null
$refs = @{}
foreach ($s in $Sample) {
    $src, $ref = $s -split "=", 2
    Copy-Item -LiteralPath $src $T
    $refs[(Split-Path $src -Leaf)] = $ref
}
# broken inputs
$rnd = New-Object byte[] 3000; (New-Object Random 7).NextBytes($rnd)
[IO.File]::WriteAllBytes("$T\corrupt.dbpr", $rnd)
[IO.File]::WriteAllText("$T\fake.pdf", "hello")
[IO.File]::WriteAllBytes("$T\empty.pdf", (New-Object byte[] 0))
[IO.File]::WriteAllText("$T\notes.txt", "x")
$pdfs = @($refs.Keys | Where-Object { $_ -like "*.pdf" })
if ($pdfs) {
    $b = [IO.File]::ReadAllBytes((Join-Path $T $pdfs[0]))
    $cut = New-Object byte[] ([Math]::Min(20000, $b.Length)); [Array]::Copy($b, $cut, $cut.Length)
    [IO.File]::WriteAllBytes("$T\truncated.pdf", $cut)
    Copy-Item (Join-Path $T $pdfs[0]) "$T\pdf_renamed.dbpr"
}

$rows = @(); $fail = 0
foreach ($f in Get-ChildItem $T -File | Where-Object { $_.Extension -notin ".json", ".csv", ".log" }) {
    $j = Join-Path $T ($f.BaseName + ".result.json")
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $p = Start-Process -FilePath $Exe -ArgumentList @("--cli", "`"$($f.FullName)`"", "--report", "`"$j`"") -Wait -PassThru
    $sw.Stop()
    $r = Get-Content -LiteralPath $j -Raw -Encoding UTF8 | ConvertFrom-Json
    $cmp = ""
    if ($refs.ContainsKey($f.Name)) {
        $same = $r.ok -and ((Get-FileHash -LiteralPath $r.out_path).Hash -eq (Get-FileHash -LiteralPath $refs[$f.Name]).Hash)
        $cmp = if ($same) { "IDENTICAL" } else { "DIFFERENT" }
        if (-not $same) { $fail++ }
    } elseif ($f.Name -eq "pdf_renamed.dbpr") {
        if (-not $r.ok) { $fail++ }
    } elseif ($r.ok -or $r.log_path) { $fail++; $cmp = "SHOULD FAIL CLEANLY" }
    $rows += [pscustomobject]@{ file = $f.Name; exit = $p.ExitCode; ms = $sw.ElapsedMilliseconds
        peakMB = [Math]::Round($r.peak_rss_bytes / 1MB, 1); csv = $cmp; message = $r.message }
}
$rows | Format-Table -AutoSize -Wrap | Out-String -Width 250
if (Get-ChildItem $T -Filter *.log) { "crash logs: " + ((Get-ChildItem $T -Filter *.log).Name -join ", "); $fail++ }
if ($fail) { "FAILED: $fail"; exit 1 } else { "ALL PASS" }
