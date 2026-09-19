using System;
using System.IO;
using UnityEngine;

namespace WarehouseRobot
{
    // Opt-in camera recording of real Play Mode physics, never a path animator.
    public sealed class UnityDemoCapture : MonoBehaviour
    {
        Camera cameraView;
        RenderTexture target;
        Texture2D pixels;
        string directory;
        StreamWriter timing;
        int frame;
        float nextCapture;
        double started;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Install()
        {
            foreach (string arg in Environment.GetCommandLineArgs())
                if (arg.StartsWith("-demoCapture=")) {
                    var capture = new GameObject("UnityDemoCapture").AddComponent<UnityDemoCapture>();
                    capture.directory = arg.Substring("-demoCapture=".Length);
                }
        }

        void Start()
        {
            Directory.CreateDirectory(directory);
            timing = new StreamWriter(Path.Combine(directory,"timestamps.csv"));
            timing.WriteLine("frame,elapsed_seconds");
            started = Time.realtimeSinceStartupAsDouble;
            cameraView = gameObject.AddComponent<Camera>();
            if (Camera.main != null) cameraView.CopyFrom(Camera.main);
            cameraView.transform.position = new Vector3(-14, 12, -10);
            cameraView.transform.LookAt(new Vector3(-3.5f, .4f, -1));
            cameraView.orthographic = true;
            cameraView.orthographicSize = 7.5f;
            cameraView.nearClipPlane=.1f;
            cameraView.farClipPlane=100;
            target = new RenderTexture(960,540,24);
            target.Create();
            pixels = new Texture2D(960,540,TextureFormat.RGB24,false);
            cameraView.targetTexture = target;
            cameraView.enabled = false;
            Application.targetFrameRate=60;
        }

        void LateUpdate()
        {
            if (Time.realtimeSinceStartup < nextCapture) return;
            nextCapture=Time.realtimeSinceStartup+1f/12f;
            cameraView.Render();
            var previous=RenderTexture.active;
            RenderTexture.active=target;
            pixels.ReadPixels(new Rect(0,0,960,540),0,0);
            pixels.Apply();
            RenderTexture.active=previous;
            File.WriteAllBytes(Path.Combine(directory,$"frame-{frame:D6}.jpg"),pixels.EncodeToJPG(88));
            timing.WriteLine(frame+","+(Time.realtimeSinceStartupAsDouble-started).ToString("F6",System.Globalization.CultureInfo.InvariantCulture));
            timing.Flush();
            frame++;
            if (File.Exists(Path.Combine(directory,"stop.txt")) || Time.realtimeSinceStartupAsDouble-started>180) {
                timing.Close();timing=null;
                enabled=false;
#if UNITY_EDITOR
                UnityEditor.EditorApplication.Exit(0);
#endif
            }
        }

        void OnDestroy()
        {
            timing?.Dispose();
            if(target!=null) target.Release();
            if(pixels!=null) Destroy(pixels);
        }
    }
}
