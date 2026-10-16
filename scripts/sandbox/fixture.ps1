# Disposable guest-only controls for testing inspection, text entry and invocation.
$ErrorActionPreference = 'Stop'
if ($env:USERNAME -ne 'WDAGUtilityAccount') { throw 'Windows Sandbox account required.' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = 'Analyst Sandbox Controller Fixture'
$form.ClientSize = New-Object Drawing.Size(440,150)
$form.StartPosition = 'CenterScreen'
$edit = New-Object Windows.Forms.TextBox
$edit.Name = 'FixtureInput'
$edit.AccessibleName = 'Fixture input'
$edit.Location = New-Object Drawing.Point(20,20)
$edit.Width = 390
$button = New-Object Windows.Forms.Button
$button.Text = 'Apply fixture text'
$button.Location = New-Object Drawing.Point(20,60)
$button.Width = 170
$label = New-Object Windows.Forms.Label
$label.Text = 'Waiting for fixture input'
$label.Location = New-Object Drawing.Point(20,105)
$label.AutoSize = $true
$button.Add_Click({
    $label.Text = 'Applied: ' + $edit.Text
    [ordered]@{ Computer=$env:COMPUTERNAME; User=$env:USERNAME;
        PID=$PID; Text=$edit.Text; Applied=$true } | ConvertTo-Json |
        Set-Content -LiteralPath 'C:\BuildOutput\controller-private\fixture-result.json' -Encoding UTF8
})
$form.Controls.AddRange(@($edit,$button,$label))
$form.ShowDialog() | Out-Null
