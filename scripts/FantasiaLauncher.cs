using System;
using System.Diagnostics;
using System.IO;
using System.Text;

internal static class FantasiaLauncher
{
    private static int Main(string[] args)
    {
        string publishRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        string runtimeRoot = Path.Combine(publishRoot, ".fantasia_runtime");
        string appExe = Path.Combine(runtimeRoot, "fantasia.exe");
        string logRoot = Path.Combine(publishRoot, "log");
        string crashlogRoot = Path.Combine(publishRoot, "crashlog");

        Directory.CreateDirectory(logRoot);
        Directory.CreateDirectory(crashlogRoot);

        if (!File.Exists(appExe))
        {
            WriteLauncherCrash(crashlogRoot, "Fantasia runtime executable was not found: " + appExe, null);
            return 2;
        }

        try
        {
            ProcessStartInfo startInfo = new ProcessStartInfo(appExe);
            startInfo.WorkingDirectory = runtimeRoot;
            startInfo.UseShellExecute = false;
            startInfo.EnvironmentVariables["FANTASIA_PORTABLE_ROOT"] = publishRoot;
            startInfo.EnvironmentVariables["FANTASIA_APP_ROOT"] = runtimeRoot;
            startInfo.EnvironmentVariables["FANTASIA_LOG_ROOT"] = logRoot;
            startInfo.EnvironmentVariables["FANTASIA_CRASHLOG_ROOT"] = crashlogRoot;
            foreach (string arg in args)
            {
                startInfo.Arguments += (startInfo.Arguments.Length == 0 ? "" : " ") + QuoteArgument(arg);
            }

            using (Process process = Process.Start(startInfo))
            {
                process.WaitForExit();
                return process.ExitCode;
            }
        }
        catch (Exception ex)
        {
            WriteLauncherCrash(crashlogRoot, ex.ToString(), ex);
            return 1;
        }
    }

    private static string QuoteArgument(string value)
    {
        if (value.Length == 0)
        {
            return "\"\"";
        }
        if (value.IndexOfAny(new[] { ' ', '\t', '\n', '\r', '"' }) < 0)
        {
            return value;
        }
        StringBuilder builder = new StringBuilder();
        builder.Append('"');
        int backslashes = 0;
        foreach (char c in value)
        {
            if (c == '\\')
            {
                backslashes++;
                continue;
            }
            if (c == '"')
            {
                builder.Append('\\', backslashes * 2 + 1);
                builder.Append('"');
                backslashes = 0;
                continue;
            }
            builder.Append('\\', backslashes);
            builder.Append(c);
            backslashes = 0;
        }
        builder.Append('\\', backslashes * 2);
        builder.Append('"');
        return builder.ToString();
    }

    private static void WriteLauncherCrash(string crashlogRoot, string message, Exception ex)
    {
        Directory.CreateDirectory(crashlogRoot);
        string path = Path.Combine(crashlogRoot, DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-launcher.log");
        File.WriteAllText(
            path,
            "Fantasia launcher crashlog" + Environment.NewLine
                + DateTime.Now.ToString("s") + Environment.NewLine
                + message + Environment.NewLine
                + (ex == null ? "" : ex.StackTrace),
            new UTF8Encoding(false)
        );
    }
}
