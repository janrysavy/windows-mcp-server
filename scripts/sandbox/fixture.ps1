# Disposable guest-only controls for testing inspection, text entry and invocation.
$ErrorActionPreference = 'Stop'
if ($env:USERNAME -ne 'WDAGUtilityAccount') { throw 'Windows Sandbox account required.' }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form = New-Object Windows.Forms.Form
$form.Text = 'Analyst Sandbox Controller Fixture'
$form.ClientSize = New-Object Drawing.Size(440,270)
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
$panel = New-Object Windows.Forms.Panel
$panel.Location = New-Object Drawing.Point(20,145)
$panel.Size = New-Object Drawing.Size(390,100)
$password = New-Object Windows.Forms.TextBox
$password.AccessibleName = 'Fixture password'
$password.PasswordChar = '*'
$password.Text = 'fixture-only-placeholder'
$password.Location = New-Object Drawing.Point(0,5)
$hidden = New-Object Windows.Forms.Label
$hidden.Text = 'Hidden native fixture label'
$hidden.Location = New-Object Drawing.Point(0,45)
$hidden.AutoSize = $true
$panel.Controls.AddRange(@($password,$hidden))
$button.Add_Click({
    $label.Text = 'Applied: ' + $edit.Text
    [ordered]@{ Computer=$env:COMPUTERNAME; User=$env:USERNAME;
        PID=$PID; Text=$edit.Text; Applied=$true } | ConvertTo-Json |
        Set-Content -LiteralPath 'C:\BuildOutput\controller-private\fixture-result.json' -Encoding UTF8
})
$form.Controls.AddRange(@($edit,$button,$label,$panel))
$form.Add_Shown({
    # Create the label HWND before hiding it, for native hidden-window enumeration.
    $hiddenHandle = $hidden.Handle
    $hidden.Visible = $false
    [ordered]@{ PID=$PID; HWND=('0x{0:X}' -f $form.Handle.ToInt64());
        HiddenHWND=('0x{0:X}' -f $hiddenHandle.ToInt64());
        PointerBits=([IntPtr]::Size*8) } | ConvertTo-Json |
        Set-Content -LiteralPath 'C:\BuildOutput\controller-private\fixture-ready.json' -Encoding UTF8
})
$form.ShowDialog() | Out-Null
