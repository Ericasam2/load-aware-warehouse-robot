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
        private const float WheelRadius = 0.18f;
        private const float TrackWidth = 0.78f;
        private const float WheelCenterHeight = 0.22f;

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

        [MenuItem("Warehouse Robotics/Upgrade Current Robot To Physical Wheels")]
        public static void UpgradeCurrentRobotToPhysicalWheels()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode)
            {
                Debug.LogError("Exit Play Mode before upgrading the robot scene.");
                return;
            }

            GameObject robot = GameObject.Find("DifferentialRobot");
            if (robot == null)
            {
                Debug.LogError("Cannot find DifferentialRobot in the active scene.");
                return;
            }

            UpgradeRobot(robot);
        }

        public static void UpgradeRobot(GameObject robot)
        {
            Undo.RegisterFullObjectHierarchyUndo(robot, "Upgrade differential-drive wheels");

            BoxCollider bodyCollider = robot.GetComponent<BoxCollider>() ??
                                       Undo.AddComponent<BoxCollider>(robot);
            bodyCollider.center = new Vector3(0.0f, 0.32f, 0.0f);
            bodyCollider.size = new Vector3(0.70f, 0.28f, 0.90f);

            Rigidbody body = robot.GetComponent<Rigidbody>() ?? Undo.AddComponent<Rigidbody>(robot);
            ConfigureRobotBody(body);

            SetChildPositionAndScale(
                robot.transform,
                "Chassis",
                new Vector3(0.0f, 0.32f, 0.0f),
                new Vector3(0.70f, 0.28f, 0.90f));
            SetChildPosition(robot.transform, "ForwardMarker", new Vector3(0.0f, 0.52f, 0.36f));
            SetChildPosition(robot.transform, "LiftColumn", new Vector3(0.0f, 0.56f, 0.0f));
            SetChildPosition(robot.transform, "LiftPlatform", new Vector3(0.0f, 0.69f, 0.0f));

            Vector3 leftPosition = new Vector3(-TrackWidth * 0.5f, WheelCenterHeight, 0.0f);
            Vector3 rightPosition = new Vector3(TrackWidth * 0.5f, WheelCenterHeight, 0.0f);
            Transform leftVisual = ConfigureExistingWheelVisual(robot.transform, "LeftWheel", leftPosition);
            Transform rightVisual = ConfigureExistingWheelVisual(robot.transform, "RightWheel", rightPosition);
            WheelCollider leftCollider = GetOrCreateWheelCollider(
                robot.transform,
                "LeftWheelCollider",
                leftPosition);
            WheelCollider rightCollider = GetOrCreateWheelCollider(
                robot.transform,
                "RightWheelCollider",
                rightPosition);

            RosDifferentialDrive drive = robot.GetComponent<RosDifferentialDrive>() ??
                                         Undo.AddComponent<RosDifferentialDrive>(robot);
            drive.Configure(
                leftCollider,
                rightCollider,
                leftVisual,
                rightVisual,
                WheelRadius,
                TrackWidth);

            RobotFunctionalModel.Apply(robot);
            EditorUtility.SetDirty(robot);
            EditorUtility.SetDirty(drive);
            EditorSceneManager.MarkSceneDirty(robot.scene);
            Selection.activeGameObject = robot;
            Debug.Log(
                "Upgraded DifferentialRobot to two torque-driven WheelColliders. " +
                "Save the scene, enter Play Mode, and test /cmd_vel.",
                robot);
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
            GameObject robot = new GameObject("DifferentialRobot");
            robot.name = "DifferentialRobot";
            robot.transform.position = Vector3.zero;

            BoxCollider bodyCollider = robot.AddComponent<BoxCollider>();
            bodyCollider.center = new Vector3(0.0f, 0.32f, 0.0f);
            bodyCollider.size = new Vector3(0.70f, 0.28f, 0.90f);

            Rigidbody body = robot.AddComponent<Rigidbody>();
            ConfigureRobotBody(body);

            GameObject chassis = GameObject.CreatePrimitive(PrimitiveType.Cube);
            chassis.name = "Chassis";
            chassis.transform.SetParent(robot.transform, false);
            chassis.transform.localPosition = new Vector3(0.0f, 0.32f, 0.0f);
            chassis.transform.localScale = new Vector3(0.70f, 0.28f, 0.90f);
            chassis.GetComponent<Collider>().enabled = false;
            chassis.GetComponent<Renderer>().sharedMaterial =
                CreateMaterial("RobotMaterial", new Color(0.10f, 0.42f, 0.80f));

            Vector3 leftWheelPosition = new Vector3(-TrackWidth * 0.5f, WheelCenterHeight, 0.0f);
            Vector3 rightWheelPosition = new Vector3(TrackWidth * 0.5f, WheelCenterHeight, 0.0f);
            Transform leftWheelVisual = CreateWheelVisual(
                robot.transform,
                "LeftWheel",
                leftWheelPosition,
                WheelRadius);
            Transform rightWheelVisual = CreateWheelVisual(
                robot.transform,
                "RightWheel",
                rightWheelPosition,
                WheelRadius);
            WheelCollider leftWheelCollider = CreateWheelCollider(
                robot.transform,
                "LeftWheelCollider",
                leftWheelPosition,
                WheelRadius);
            WheelCollider rightWheelCollider = CreateWheelCollider(
                robot.transform,
                "RightWheelCollider",
                rightWheelPosition,
                WheelRadius);

            RosDifferentialDrive drive = robot.AddComponent<RosDifferentialDrive>();
            drive.Configure(
                leftWheelCollider,
                rightWheelCollider,
                leftWheelVisual,
                rightWheelVisual,
                WheelRadius,
                TrackWidth);

            GameObject forwardMarker = GameObject.CreatePrimitive(PrimitiveType.Cube);
            forwardMarker.name = "ForwardMarker";
            forwardMarker.transform.SetParent(robot.transform, false);
            forwardMarker.transform.localPosition = new Vector3(0.0f, 0.52f, 0.36f);
            forwardMarker.transform.localScale = new Vector3(0.22f, 0.10f, 0.15f);
            forwardMarker.GetComponent<Collider>().enabled = false;
            forwardMarker.GetComponent<Renderer>().sharedMaterial =
                CreateMaterial("ForwardMarkerMaterial", new Color(1.0f, 0.55f, 0.05f));

            Transform liftPlatform = CreateLift(robot.transform);
            RosLiftController liftController = robot.AddComponent<RosLiftController>();
            liftController.Configure(liftPlatform);
            RobotFunctionalModel.Apply(robot);
        }

        private static Transform CreateWheelVisual(
            Transform parent,
            string name,
            Vector3 localPosition,
            float radius)
        {
            GameObject wheel = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            wheel.name = name;
            wheel.transform.SetParent(parent, false);
            wheel.transform.localPosition = localPosition;
            wheel.transform.localRotation = Quaternion.Euler(0.0f, 0.0f, 90.0f);
            wheel.transform.localScale = new Vector3(radius * 2, 0.08f, radius * 2);
            wheel.GetComponent<Collider>().enabled = false;
            wheel.GetComponent<Renderer>().sharedMaterial =
                CreateMaterial("WheelMaterial", new Color(0.04f, 0.04f, 0.04f));

            return wheel.transform;
        }

        private static WheelCollider CreateWheelCollider(
            Transform parent,
            string name,
            Vector3 localPosition,
            float radius)
        {
            GameObject wheelObject = new GameObject(name);
            wheelObject.transform.SetParent(parent, false);
            wheelObject.transform.localPosition = localPosition;
            WheelCollider wheelCollider = wheelObject.AddComponent<WheelCollider>();
            wheelCollider.radius = radius;
            return wheelCollider;
        }

        private static void ConfigureRobotBody(Rigidbody body)
        {
            body.mass = 40.0f;
            body.useGravity = true;
            body.linearDamping = 0.1f;
            body.angularDamping = 0.5f;
            body.centerOfMass = new Vector3(0.0f, 0.24f, 0.0f);
            body.solverIterations = 12;
            body.solverVelocityIterations = 12;
        }

        private static Transform ConfigureExistingWheelVisual(
            Transform parent,
            string name,
            Vector3 localPosition)
        {
            Transform visual = parent.Find(name);
            if (visual == null)
            {
                return CreateWheelVisual(parent, name, localPosition, WheelRadius);
            }

            visual.localPosition = localPosition;
            visual.localRotation = Quaternion.Euler(0.0f, 0.0f, 90.0f);
            visual.localScale = new Vector3(WheelRadius * 2, 0.08f, WheelRadius * 2);
            Collider visualCollider = visual.GetComponent<Collider>();
            if (visualCollider != null)
            {
                visualCollider.enabled = false;
            }

            return visual;
        }

        private static WheelCollider GetOrCreateWheelCollider(
            Transform parent,
            string name,
            Vector3 localPosition)
        {
            Transform existing = parent.Find(name);
            WheelCollider wheelCollider;
            if (existing == null)
            {
                GameObject wheelObject = new GameObject(name);
                Undo.RegisterCreatedObjectUndo(wheelObject, $"Create {name}");
                wheelObject.transform.SetParent(parent, false);
                wheelCollider = wheelObject.AddComponent<WheelCollider>();
            }
            else
            {
                wheelCollider = existing.GetComponent<WheelCollider>() ??
                                Undo.AddComponent<WheelCollider>(existing.gameObject);
            }

            wheelCollider.transform.localPosition = localPosition;
            wheelCollider.transform.localRotation = Quaternion.identity;
            wheelCollider.radius = WheelRadius;
            return wheelCollider;
        }

        private static void SetChildPosition(Transform parent, string name, Vector3 localPosition)
        {
            Transform child = parent.Find(name);
            if (child != null)
            {
                child.localPosition = localPosition;
            }
        }

        private static void SetChildPositionAndScale(
            Transform parent,
            string name,
            Vector3 localPosition,
            Vector3 localScale)
        {
            Transform child = parent.Find(name);
            if (child != null)
            {
                child.localPosition = localPosition;
                child.localScale = localScale;
            }
        }

        private static Transform CreateLift(Transform parent)
        {
            Material liftMaterial = CreateMaterial("LiftMaterial", new Color(0.95f, 0.72f, 0.10f));

            GameObject column = GameObject.CreatePrimitive(PrimitiveType.Cube);
            column.name = "LiftColumn";
            column.transform.SetParent(parent, false);
            column.transform.localPosition = new Vector3(0.0f, 0.56f, 0.0f);
            column.transform.localScale = new Vector3(0.16f, 0.18f, 0.16f);
            column.GetComponent<Collider>().enabled = false;
            column.GetComponent<Renderer>().sharedMaterial = liftMaterial;

            GameObject platform = GameObject.CreatePrimitive(PrimitiveType.Cube);
            platform.name = "LiftPlatform";
            platform.transform.SetParent(parent, false);
            platform.transform.localPosition = new Vector3(0.0f, 0.69f, 0.0f);
            platform.transform.localScale = new Vector3(0.62f, 0.08f, 0.72f);
            platform.GetComponent<Renderer>().sharedMaterial = liftMaterial;

            return platform.transform;
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
            camera.transform.LookAt(new Vector3(0.0f, 0.35f, 0.0f));
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
