$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
# SVGEdit targets the active window. Serialize concurrent conversions in this
# desktop session before opening a window or changing the active selection.
$gate = [Threading.Mutex]::new($false, 'Local\mpl2pptx.SVGEdit')
try { [void]$gate.WaitOne() } catch [Threading.AbandonedMutexException] { }
$app = $null
$presentation = $null
try {
    $app = New-Object -ComObject PowerPoint.Application
    $presentation = $app.Presentations.Add(-1)
    $w = [single]$env:MPL_SLIDE_W
    $h = [single]$env:MPL_SLIDE_H
    $presentation.PageSetup.SlideWidth = $w
    $presentation.PageSetup.SlideHeight = $h
    $slide = $presentation.Slides.Add(1, 12)
    $window = $presentation.Windows.Item(1)
    $window.Activate()
    $window.View.GotoSlide(1)
    $picture = $slide.Shapes.AddPicture($env:MPL_FIGURE_SVG, 0, -1, 0, 0, $w, $h)
    $picture.Select()
    if (-not $app.CommandBars.GetEnabledMso('SVGEdit')) {
        throw 'This desktop version of PowerPoint does not offer Convert to Shape (SVGEdit).'
    }
    $app.CommandBars.ExecuteMso('SVGEdit')
    if ($slide.Shapes.Count -eq 1 -and $slide.Shapes.Item(1).Type -eq 28) {
        throw 'PowerPoint left the SVG unconverted.'
    }
    # Ungroup in PowerPoint so each child has absolute slide coordinates.
    do {
        $found = $false
        for ($i = $slide.Shapes.Count; $i -ge 1; $i--) {
            $s = $slide.Shapes.Item($i)
            if ($s.Type -eq 6) {
                $null = $s.Ungroup()
                $found = $true
            }
        }
    } while ($found)
    $presentation.SaveAs($env:MPL_FIGURE_STAGE, 24)
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    try {
        if ($null -ne $presentation) {
            $presentation.Saved = -1
            $presentation.Close()
        }
        if ($null -ne $app) { [void][Runtime.InteropServices.Marshal]::ReleaseComObject($app) }
    } finally {
        $gate.ReleaseMutex()
        $gate.Dispose()
    }
}
