using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace WarehouseRobot.Editor
{
    public static class BuildMinimalRobotScene
    {
        private const string SceneFolder = "Assets/Scenes";
        private const string ScenePath = SceneFolder + "/MinimalRosRobot.unity";

        [MenuItem("Warehouse Robotics/Build Minimal ROS Robot Scene")]
        public static void BuildScene()
        {
            EnsureFolder("Assets", "Scenes");

            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            scene.name = "MinimalRosRobot";

            CreateGround();
            CreateRobot();
            CreateLighting();
            CreateCamera();

            EditorSceneManager.SaveScene(scene, ScenePath);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(ScenePath, true) };
            Selection.activeGameObject = GameObject.Find("DifferentialRobot");
            Debug.Log($"Created minimal ROS robot scene at {ScenePath}");
        }

        private static void CreateGround()
        {
            GameObject ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.name = "Ground";
            ground.transform.localScale = new Vector3(2.0f, 1.0f, 2.0f);

            Renderer renderer = ground.GetComponent<Renderer>();
            renderer.sharedMaterial = CreateMaterial("GroundMaterial", new Color(0.18f, 0.20f, 0.22f));
        }

        private static void CreateRobot()
        {
            GameObject robot = GameObject.CreatePrimitive(PrimitiveType.Cube);
            robot.name = "DifferentialRobot";
            robot.transform.position = new Vector3(0.0f, 0.30f, 0.0f);
            robot.transform.localScale = new Vector3(0.70f, 0.30f, 0.90f);

            Rigidbody body = robot.AddComponent<Rigidbody>();
            body.mass = 40.0f;
            body.useGravity = true;
            body.linearDamping = 0.2f;
            body.angularDamping = 1.0f;
            robot.AddComponent<RosDifferentialDrive>();

            Renderer renderer = robot.GetComponent<Renderer>();
            renderer.sharedMaterial = CreateMaterial("RobotMaterial", new Color(0.10f, 0.42f, 0.80f));

            CreateWheel(robot.transform, "LeftWheel", new Vector3(-0.42f, -0.10f, 0.0f));
            CreateWheel(robot.transform, "RightWheel", new Vector3(0.42f, -0.10f, 0.0f));

            GameObject forwardMarker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            forwardMarker.name = "ForwardMarker";
            forwardMarker.transform.SetParent(robot.transform, false);
            forwardMarker.transform.localPosition = new Vector3(0.0f, 0.28f, 0.36f);
            forwardMarker.transform.localScale = new Vector3(0.22f, 0.10f, 0.15f);
            forwardMarker.GetComponent<Collider>().enabled = false;
            forwardMarker.GetComponent<Renderer>().sharedMaterial =
                CreateMaterial("ForwardMarkerMaterial", new Color(1.0f, 0.55f, 0.05f));
        }

        private static void CreateWheel(Transform parent, string name, Vector3 localPosition)
        {
            GameObject wheel = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            wheel.name = name;
            wheel.transform.SetParent(parent, false);
            wheel.transform.localPosition = localPosition;
            wheel.transform.localRotation = Quaternion.Euler(0.0f, 0.0f, 90.0f);
            wheel.transform.localScale = new Vector3(0.28f, 0.10f, 0.28f);
            wheel.GetComponent<Collider>().enabled = false;
            wheel.GetComponent<Renderer>().sharedMaterial =
                CreateMaterial("WheelMaterial", new Color(0.04f, 0.04f, 0.04f));
        }

        private static void CreateLighting()
        {
            GameObject lightObject = new GameObject("Directional Light");
            Light light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.2f;
            lightObject.transform.rotation = Quaternion.Euler(45.0f, -30.0f, 0.0f);
        }

        private static void CreateCamera()
        {
            GameObject cameraObject = new GameObject("Main Camera");
            cameraObject.tag = "MainCamera";
            Camera camera = cameraObject.AddComponent<Camera>();
            cameraObject.AddComponent<AudioListener>();
            camera.transform.position = new Vector3(4.5f, 5.0f, -5.5f);
            camera.transform.LookAt(new Vector3(0.0f, 0.2f, 0.0f));
        }

        private static Material CreateMaterial(string name, Color color)
        {
            const string materialFolder = "Assets/Materials";
            EnsureFolder("Assets", "Materials");
            string path = $"{materialFolder}/{name}.mat";

            Material material = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (material != null)
            {
                return material;
            }

            Shader shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            material = new Material(shader) { color = color };
            AssetDatabase.CreateAsset(material, path);
            return material;
        }

        private static void EnsureFolder(string parent, string child)
        {
            string path = $"{parent}/{child}";
            if (!AssetDatabase.IsValidFolder(path))
            {
                AssetDatabase.CreateFolder(parent, child);
            }
        }
    }
}
