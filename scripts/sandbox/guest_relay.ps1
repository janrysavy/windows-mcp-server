param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{32}$')][string]$Connection)
$ErrorActionPreference = 'Stop'
if ($env:USERNAME -ne 'WDAGUtilityAccount') { throw 'Windows Sandbox account required.' }
$incoming = 'C:\BuildInput\mcp-transport\' + $Connection
$outgoing = 'C:\BuildOutput\controller-private\' + $Connection
New-Item -ItemType Directory -Path $outgoing -Force | Out-Null
trap {
    # Private diagnostics; do not surface exception details through MCP stdout.
    [IO.File]::WriteAllText(($outgoing + '\startup-error.txt'), ($_ | Out-String))
    exit 1
}
$server = 'C:\BuildInput\windows-mcp-server.exe'
$settings = Get-Content -LiteralPath ($incoming + '\settings.json') -Raw | ConvertFrom-Json
$expected = [string]$settings.ServerSha256
if ($expected -notmatch '^[a-fA-F0-9]{64}$') { throw 'Expected server SHA256 required.' }
if ((Get-FileHash -LiteralPath $server -Algorithm SHA256).Hash -ne $expected) {
    throw 'Unexpected MCP server binary.'
}
Add-Type -TypeDefinition @'
using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
public static class SandboxMcpRelay {
    static readonly Encoding Utf8 = new UTF8Encoding(false);
    static void Publish(string dir, string name, string data) {
        string path=Path.Combine(dir,name), tmp=path+".tmp";
        File.WriteAllText(tmp,data,Utf8); File.Move(tmp,path);
    }
    public static int Run(string executable,string incoming,string outgoing) {
        // Framework has no ProcessStartInfo.StandardInputEncoding. Process.Start
        // uses Console.InputEncoding and AutoFlush can emit its BOM immediately.
        Console.InputEncoding=Utf8;
        var psi=new ProcessStartInfo(executable,
            "stdio --toolsets screen,interaction,apps --exclude-tools Recording");
        psi.UseShellExecute=false; psi.CreateNoWindow=true;
        psi.RedirectStandardInput=true; psi.RedirectStandardOutput=true;
        psi.RedirectStandardError=true;
        psi.StandardOutputEncoding=Utf8; psi.StandardErrorEncoding=Utf8;
        using(var p=Process.Start(psi)) {
            Publish(outgoing,"status.json","{\"GuestPid\":"+p.Id+
                ",\"Server\":\"windows-mcp-server\",\"HostUiAccess\":false}");
            Exception outputError=null;
            var output=new Thread(()=> {
                try { int i=1; string line;
                    while((line=p.StandardOutput.ReadLine())!=null)
                        Publish(outgoing,(i++).ToString("D8")+".json",line);
                } catch(Exception e) { outputError=e; }
            });
            // This directory is private transport storage, never a commit artifact.
            var diagnostic=new StringBuilder();
            var error=new Thread(()=> { try { string line;
                while((line=p.StandardError.ReadLine())!=null) {
                    if(diagnostic.Length<32768) diagnostic.AppendLine(line);
                } }
                catch(IOException) {} });
            output.IsBackground=true; error.IsBackground=true;
            output.Start(); error.Start();
            int next=1; var activity=Stopwatch.StartNew();
            try {
                while(!p.HasExited && outputError==null) {
                    string request=Path.Combine(incoming,next.ToString("D8")+".json");
                    if(File.Exists(request)) {
                        // .NET Framework's redirected StreamWriter emits a UTF-8 BOM.
                        // MCP JSON framing forbids that preamble; write explicit bytes.
                        byte[] frame=Utf8.GetBytes(File.ReadAllText(request,Utf8).TrimEnd('\r','\n')+"\n");
                        p.StandardInput.BaseStream.Write(frame,0,frame.Length);
                        p.StandardInput.BaseStream.Flush(); next++; activity.Restart(); continue;
                    }
                    if(File.Exists(Path.Combine(incoming,"stop.json")) ||
                       activity.Elapsed.TotalMinutes>15) break;
                    Thread.Sleep(30);
                }
            } finally {
                p.StandardInput.BaseStream.Close();
                if(!p.WaitForExit(2000)) p.Kill();
                p.WaitForExit(); output.Join(2000); error.Join(2000);
            }
            if(outputError!=null) throw new IOException("MCP output publication failed",outputError);
            Publish(outgoing,"stderr.txt",diagnostic.ToString());
            Publish(outgoing,"exit.json","{\"ExitCode\":"+p.ExitCode+"}");
            return p.ExitCode;
        }
    }
}
'@
exit [SandboxMcpRelay]::Run($server,$incoming,$outgoing)
