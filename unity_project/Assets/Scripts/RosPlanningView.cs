using System;
using RosMessageTypes.Nav;
using RosMessageTypes.Std;
using Unity.Robotics.ROSTCPConnector;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace WarehouseRobot
{
    // Runtime-only helper: does not change the saved warehouse/map geometry.
    public sealed class RosPlanningView : MonoBehaviour
    {
        [Serializable] private class Context
        {
            public string scene;
            public float[] map_from_odom;
        }
        private ROSConnection ros;
        private string context;
        private float nextPublish;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            var robot = GameObject.Find("DifferentialRobot");
            if (robot != null && robot.GetComponent<RosPlanningView>() == null)
                robot.AddComponent<RosPlanningView>();
        }

        private void Start()
        {
            ros = ROSConnection.GetOrCreateInstance();
            ros.RegisterPublisher<StringMsg>("/warehouse/test_context");
            context = JsonUtility.ToJson(new Context {
                scene = SceneManager.GetActiveScene().name,
                map_from_odom = new[] {transform.position.z, -transform.position.x,
                    -Mathf.DeltaAngle(0, transform.eulerAngles.y) * Mathf.Deg2Rad}
            });
            ros.Subscribe<PathMsg>("/planned_path", DrawPath);
        }

        private void Update()
        {
            if (Time.unscaledTime < nextPublish) return;
            nextPublish = Time.unscaledTime + 0.5f;
            ros.Publish("/warehouse/test_context", new StringMsg(context));
        }

        private void DrawPath(PathMsg message)
        {
            if (message.header.frame_id != "map") return;
            var line = GameObject.Find("AStarPlannedPath");
            if (line == null) line = new GameObject("AStarPlannedPath");
            var renderer = line.GetComponent<LineRenderer>();
            if (renderer == null) {
                renderer = line.AddComponent<LineRenderer>();
                renderer.material = new Material(Shader.Find("Sprites/Default"));
            }
            renderer.useWorldSpace = true;
            renderer.startWidth = renderer.endWidth = .035f;
            renderer.startColor = renderer.endColor = Color.cyan;
            renderer.positionCount = message.poses.Length;
            for (int i = 0; i < message.poses.Length; i++) {
                var p = message.poses[i].pose.position;
                renderer.SetPosition(i, new Vector3(-(float)p.y, .035f, (float)p.x));
            }
        }
    }
}
