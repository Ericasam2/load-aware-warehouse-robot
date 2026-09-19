using System;
using UnityEditor;
using UnityEditor.SceneManagement;

// Batch smoke test uses the saved scene; never rebuilds or saves user geometry.
[InitializeOnLoad]
public static class RunRosUnityTest
{
    const string DeadlineKey = "WarehouseRosTestDeadline";
    static RunRosUnityTest()
    {
        EditorApplication.update += Watchdog;
    }

    public static void Begin()
    {
        EditorSceneManager.OpenScene("Assets/Scenes/WarehouseEnvironment.unity");
        SessionState.SetString(DeadlineKey, DateTime.UtcNow.AddSeconds(300).ToString("O"));
        EditorApplication.EnterPlaymode();
    }

    static void Watchdog()
    {
        string value = SessionState.GetString(DeadlineKey, "");
        if (value.Length == 0 || DateTime.UtcNow < DateTime.Parse(value).ToUniversalTime()) return;
        SessionState.EraseString(DeadlineKey);
        if (UnityEngine.Application.isBatchMode) EditorApplication.Exit(0);
        else EditorApplication.ExitPlaymode();
    }
}
