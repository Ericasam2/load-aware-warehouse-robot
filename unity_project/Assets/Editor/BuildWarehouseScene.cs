using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace WarehouseRobot.Editor
{
    /// <summary>Metre-scale warehouse; generated assets never overwrite the source robot scene.</summary>
    public static class BuildWarehouseScene
    {
        public const string ScenePath = "Assets/Scenes/WarehouseEnvironment.unity";
        private static Transform root;
        private static Material floor, steel, orange, concrete, yellow, green, blue, carton;

        [MenuItem("Warehouse Robotics/Build Warehouse Environment")]
        public static void Build()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode) return;
            if (!Application.isBatchMode && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo()) return;
            // Save prompt above protects editor work; run only one robot/ROS publisher scene.
            Scene previousWarehouse = SceneManager.GetSceneByPath(ScenePath);
            if (previousWarehouse.IsValid() && previousWarehouse.isLoaded)
                EditorSceneManager.CloseScene(previousWarehouse, true);
            string sourceCopy = AssetDatabase.GenerateUniqueAssetPath("Assets/Scenes/WarehouseBuildSource.unity");
            if (!AssetDatabase.CopyAsset("Assets/Scenes/MinimalRosRobot.unity", sourceCopy))
                throw new IOException("Could not copy source robot scene");
            Scene scene = EditorSceneManager.OpenScene(sourceCopy, OpenSceneMode.Single);
            EditorSceneManager.SetActiveScene(scene);
            root = new GameObject("WarehouseEnvironment").transform;
            floor = Mat("Floor", new Color(.19f,.23f,.27f));
            steel = Mat("Steel", new Color(.12f,.24f,.34f));
            orange = Mat("RackBeam", new Color(.95f,.37f,.08f));
            concrete = Mat("Wall", new Color(.58f,.64f,.67f));
            yellow = Mat("Safety", new Color(1f,.76f,.12f));
            green = Mat("Delivery", new Color(.15f,.75f,.52f));
            blue = Mat("Pickup", new Color(.18f,.62f,.95f));
            carton = Mat("Carton", new Color(.66f,.45f,.25f));
            GameObject robot = scene.GetRootGameObjects().Single(o => o.name == "DifferentialRobot");
            // The saved source predates the physical-wheel upgrade. Upgrade only this copy.
            Selection.activeGameObject = robot;
            BuildMinimalRobotScene.UpgradeRobot(robot);
            robot.transform.SetPositionAndRotation(new Vector3(-7,0,-6), Quaternion.identity);
            foreach (var o in scene.GetRootGameObjects().Where(o => o.name == "Ground").ToArray())
                UnityEngine.Object.DestroyImmediate(o);
            Box("Floor", new Vector3(0,-.15f,0), new Vector3(20,.3f,18), floor);
            Box("WestWall", new Vector3(-10,1.5f,0), new Vector3(.2f,3,18), concrete);
            Box("EastWall", new Vector3(10,1.5f,0), new Vector3(.2f,3,18), concrete);
            Box("NorthWall", new Vector3(0,1.5f,9), new Vector3(20,3,.2f), concrete);
            Box("SouthBarrier", new Vector3(0,.25f,-9), new Vector3(20,.5f,.2f), concrete);
            TransferRack(new Vector3(-5,0,2), "P1_PICKUP_RACK", true);
            TransferRack(new Vector3(0,0,2), "P2_DROPOFF_RACK", false);
            ThroughRack(new Vector3(5,0,2));
            Pad("START", new Vector3(-7,0,-6), blue);
            var obstacle = Box("TemporaryObstacle_MOVE_IN_EDITOR", new Vector3(8,.5f,7), Vector3.one, orange);
            Label("TEMP OBSTACLE", new Vector3(8,1.1f,7), .16f);
            Marker("RobotStart", new Vector3(-7,0,-6));
            Marker("Pickup_P1", new Vector3(-5,0,2));
            Marker("Dropoff_P2", new Vector3(0,0,2));
            Marker("LowGate", new Vector3(-5,0,0));
            Marker("HighGate", new Vector3(5,0,0));
            Marker("PickupSideExit", new Vector3(-2.5f,0,2));
            for (int i=-8; i<=8; i+=2)
                Box("LaneDash", new Vector3(i,.006f,-3), new Vector3(.8f,.008f,.06f), yellow, false);
            var camera = scene.GetRootGameObjects().SelectMany(o => o.GetComponentsInChildren<Camera>()).First();
            camera.transform.position = new Vector3(13,26,-19);
            camera.transform.LookAt(new Vector3(0,0,1));
            camera.orthographic = true;
            camera.orthographicSize = 13;
            camera.backgroundColor = new Color(.07f,.10f,.15f);
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.farClipPlane = 100;
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = new Color(.32f,.36f,.42f);
            foreach (var light in scene.GetRootGameObjects().SelectMany(o => o.GetComponentsInChildren<Light>()))
            { light.shadows = LightShadows.Soft; light.intensity = .9f; }
            Physics.SyncTransforms();
            Validate(scene, robot);
            EditorSceneManager.SaveScene(scene, ScenePath);
            AssetDatabase.DeleteAsset(sourceCopy);
            AssetDatabase.SaveAssets();
            var scenes = EditorBuildSettings.scenes.Where(s => s.path != ScenePath).ToList();
            scenes.Add(new EditorBuildSettingsScene(ScenePath,true));
            EditorBuildSettings.scenes = scenes.ToArray();
            RenderPreview(camera);
            RenderRackDetails(camera, robot);
            Debug.Log("WAREHOUSE_BUILD_OK: " + ScenePath);
        }

        private static void RackFrame(Vector3 p, float underside)
        {
            for(int x=-1;x<=1;x+=2) for(int z=-1;z<=1;z+=2)
                Box("SideUpright",p+new Vector3(x*1.08f,1.6f,z*2),new Vector3(.16f,3.2f,.16f),steel);
            Box("OverheadStorageDeck",p+new Vector3(0,underside+.06f,0),new Vector3(2.0f,.12f,3.76f),orange);
            foreach(float x in new[]{-1.08f,1.08f})
                Box("UpperSideBrace",p+new Vector3(x,underside+.19f,0),new Vector3(.16f,.26f,4.16f),steel);
            for(int z=-1;z<=1;z++)
                Box("OverheadCarton",p+new Vector3(0,underside+.42f,z*1.15f),new Vector3(1.5f,.6f,.9f),carton);
        }

        private static void TransferRack(Vector3 p,string name,bool cargo)
        {
            var saved=root;root=new GameObject(name).transform;root.SetParent(saved);
            RackFrame(p,2.2f);
            // Low entrance/exit are part of this rack; the centre is open overhead for lifting.
            foreach(float z in new[]{-2f,2f})
                Box("LowClearanceCrossbeam",p+new Vector3(0,1.06f,z),new Vector3(2.0f,.12f,.24f),yellow);
            StaticConveyorLift(p);
            if(cargo)
            {
                var deck=Box("PickupCargo",p+new Vector3(0,.88f,0),new Vector3(1.7f,.12f,1.4f),carton);
                var load=Box("CargoBox",p+new Vector3(0,1.24f,0),new Vector3(1.2f,.6f,1.1f),blue);
                load.transform.SetParent(deck.transform,true);
            }
            Box("UnderRackLane",p+new Vector3(0,.008f,0),new Vector3(1.26f,.01f,5.3f),blue,false);
            Box("SideTransferExit",p+new Vector3(0,.009f,0),new Vector3(4.3f,.01f,1.16f),green,false);
            Label(cargo?"P1 / PICKUP":"P2 / DROP",p+new Vector3(0,.035f,-3.05f),.23f);
            Label("LOW ENTRY / 1.0 m",p+new Vector3(0,.035f,-2.5f),.15f);
            Label("LIFT + SIDE EXIT",p+new Vector3(1.7f,.035f,.85f),.12f);
            root=saved;
        }

        private static void StaticConveyorLift(Vector3 p)
        {
            var saved=root;root=new GameObject("StaticOpenCenterConveyorLift").transform;root.SetParent(saved);
            var belt=Mat("ConveyorBelt",new Color(.065f,.085f,.10f));
            var roller=Mat("ConveyorRoller",new Color(.50f,.57f,.61f));
            // Twin tracks run along X. The uninterrupted central slot is 1.12 m wide (Z).
            // Entire track underside stays above 0.76 m for retracted longitudinal passage.
            foreach(float z in new[]{-.64f,.64f})
            {
                Box("TrackSideFrame",p+new Vector3(0,.785f,z),new Vector3(3.48f,.050f,.16f),steel);
                Box("UpperBeltContact",p+new Vector3(0,.815f,z),new Vector3(3.48f,.010f,.16f),belt);
                Box("LowerBeltReturn",p+new Vector3(0,.764f,z),new Vector3(3.48f,.006f,.14f),belt,false);
                for(int i=0;i<44;i++)
                    Box("TreadLink",p+new Vector3(-1.72f+i*.08f,.821f,z),new Vector3(.009f,.002f,.15f),roller,false);
                foreach(float x in new[]{-1.77f,1.77f})
                {
                    var drum=GameObject.CreatePrimitive(PrimitiveType.Cylinder);drum.name="StaticEndRoller";
                    drum.transform.SetParent(root);drum.transform.position=p+new Vector3(x,.79f,z);
                    drum.transform.rotation=Quaternion.Euler(90,0,0);drum.transform.localScale=new Vector3(.06f,.08f,.06f);
                    UnityEngine.Object.DestroyImmediate(drum.GetComponent<Collider>());
                    drum.GetComponent<Renderer>().sharedMaterial=roller;
                }
                foreach(float x in new[]{-1.30f,1.30f})
                {
                    Box("OutboardSupportLeg",p+new Vector3(x,.375f,z),new Vector3(.12f,.75f,.14f),steel);
                    Box("AnchorFoot",p+new Vector3(x,.025f,z),new Vector3(.24f,.05f,.22f),yellow);
                }
            }
            // Static lift guides flank the exit and never bridge the robot's floor-level route.
            foreach(float z in new[]{-1.02f,1.02f})
            {
                Box("LiftGuideTower",p+new Vector3(1.42f,.95f,z),new Vector3(.16f,1.90f,.14f),steel);
                Box("LiftGuideRail",p+new Vector3(1.325f,1.0f,z),new Vector3(.025f,1.6f,.055f),roller);
                Box("FixedLiftCarriage",p+new Vector3(1.30f,.79f,z),new Vector3(.16f,.24f,.20f),yellow);
                Box("CarriageToTrackBracket",p+new Vector3(1.30f,.785f,z*.80f),new Vector3(.12f,.05f,.30f),steel);
                Box("TowerFoot",p+new Vector3(1.42f,.035f,z),new Vector3(.32f,.07f,.28f),steel);
            }
            Box("StaticDriveHousing",p+new Vector3(-1.60f,.88f,1.01f),new Vector3(.30f,.24f,.24f),orange);
            Box("DriveMount",p+new Vector3(-1.60f,.785f,.855f),new Vector3(.26f,.05f,.27f),steel);
            Label("OPEN CENTER / 1.12 m",p+new Vector3(0,.03f,0),.13f);
            foreach(var t in root.GetComponentsInChildren<Transform>()) t.gameObject.isStatic=true;
            root=saved;
        }

        private static void ThroughRack(Vector3 p)
        {
            var saved=root;root=new GameObject("HIGH_THROUGH_RACK").transform;root.SetParent(saved);
            RackFrame(p,2.4f);
            foreach(float z in new[]{-2f,2f})
                Box("HighClearanceCrossbeam",p+new Vector3(0,2.46f,z),new Vector3(2.0f,.12f,.24f),green);
            Box("LoadedThroughLane",p+new Vector3(0,.008f,0),new Vector3(1.96f,.01f,5.3f),green,false);
            Label("HIGH / LOADED",p+new Vector3(0,.035f,-3.05f),.23f);
            Label("2.0 m W / 2.4 m H",p+new Vector3(0,.035f,-2.5f),.15f);
            root=saved;
        }

        private static void Pad(string name,Vector3 p,Material color)
        {
            Box(name+"_Pad",p+new Vector3(0,.007f,0),new Vector3(2.3f,.01f,2.3f),color,false);
            Label(name,p+new Vector3(0,.035f,-1.5f),.22f);
        }
        private static void Marker(string name,Vector3 p)
        { var o=new GameObject(name);o.transform.SetParent(root);o.transform.position=p; }
        private static GameObject Box(string name,Vector3 p,Vector3 size,Material mat,bool solid=true)
        {
            var o=GameObject.CreatePrimitive(PrimitiveType.Cube);o.name=name;o.transform.SetParent(root);
            o.transform.position=p;o.transform.localScale=size;o.GetComponent<Renderer>().sharedMaterial=mat;
            if(!solid) UnityEngine.Object.DestroyImmediate(o.GetComponent<Collider>());
            return o;
        }
        private static void Label(string text,Vector3 p,float size)
        {
            var o=new GameObject(text);o.transform.SetParent(root);o.transform.position=p;
            o.transform.rotation=Quaternion.Euler(90,0,0);
            var t=o.AddComponent<TextMesh>();t.text=text;t.anchor=TextAnchor.MiddleCenter;
            t.alignment=TextAlignment.Center;t.fontSize=64;t.characterSize=size*.22f;t.color=Color.white;
        }
        private static Material Mat(string name,Color color)
        {
            const string folder="Assets/Materials/Warehouse";
            if(!AssetDatabase.IsValidFolder(folder)) AssetDatabase.CreateFolder("Assets/Materials","Warehouse");
            string path=folder+"/"+name+".mat";
            var m=AssetDatabase.LoadAssetAtPath<Material>(path);
            if(m==null) {m=new Material(Shader.Find("Standard"));AssetDatabase.CreateAsset(m,path);}
            m.color=color;m.SetFloat("_Glossiness",.18f);return m;
        }
        private static void Validate(Scene scene,GameObject robot)
        {
            if(robot.GetComponentsInChildren<WheelCollider>().Length!=2) throw new Exception("Expected two physical wheels");
            ValidateRackPassages(scene,robot);
            if(Physics.CheckBox(robot.transform.position+Vector3.up*.45f,new Vector3(.5f,.4f,.55f),Quaternion.identity,
                ~0,QueryTriggerInteraction.Ignore) && Physics.OverlapBox(robot.transform.position+Vector3.up*.45f,
                    new Vector3(.5f,.4f,.55f)).Any(c=> !c.transform.IsChildOf(robot.transform)))
                throw new Exception("Robot spawn overlaps warehouse geometry");
            Debug.Log("WAREHOUSE_VALIDATION_OK: spawn, wheels, full-length under-rack passages");
        }

        public static void ValidateRackPassages(Scene scene,GameObject robot)
        {
            // Conservative envelopes include the full visual wheel width and platform height.
            for(int i=0;i<=60;i++)
            {
                float z=-1+i*.1f;
                foreach(float x in new[]{-5f,0f,5f})
                    if(Physics.CheckBox(new Vector3(x,.39f,z),new Vector3(.49f,.36f,.46f)))
                        throw new Exception("Retracted robot blocked under rack: "+x+", "+z);
                if(Physics.CheckBox(new Vector3(5,.93f,z),new Vector3(.86f,.91f,.71f)))
                    throw new Exception("Loaded envelope blocked under high rack: "+z);
            }
            foreach(float x in new[]{-5f,0f})
            foreach(float z in new[]{0f,4f})
                if(!Physics.CheckBox(new Vector3(x,.57f,z),new Vector3(.49f,.53f,.46f)))
                    throw new Exception("Raised platform should be blocked by low rack entrance");

            // Validate pickup lift and lateral exit with actual compound robot + pallet colliders.
            var originalPosition=robot.transform.position;var originalRotation=robot.transform.rotation;
            var platform=robot.transform.Find("LiftPlatform");var originalPlatform=platform.localPosition;
            var cargo=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>())
                .Single(t=>t.name=="PickupCargo");
            var cargoPosition=cargo.position;
            var moving=robot.GetComponentsInChildren<BoxCollider>().Where(c=>c.enabled)
                .Concat(cargo.GetComponentsInChildren<BoxCollider>()).ToArray();
            var obstacles=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<BoxCollider>())
                .Where(c=>c.enabled && !moving.Contains(c)).ToArray();
            try
            {
                // A 90 degree turn is done before entering laterally; do not rotate between supports.
                robot.transform.rotation=Quaternion.Euler(0,90,0);
                robot.transform.position=new Vector3(-5,0,2);
                for(int step=0;step<=35;step++)
                {
                    float extension=step*.01f;
                    platform.localPosition=new Vector3(0,.69f+extension,0);
                    cargo.position=cargoPosition+Vector3.up*Mathf.Max(0,extension-.09f);
                    Physics.SyncTransforms();
                    if(moving.Any(a=>obstacles.Any(b=>Physics.ComputePenetration(a,a.transform.position,a.transform.rotation,
                        b,b.transform.position,b.transform.rotation,out _,out float depth) && depth > .0001f)))
                        throw new Exception("Pickup vertical envelope collides at lift "+extension);
                }
                platform.localPosition=new Vector3(0,1.04f,0);
                for(int i=0;i<=50;i++)
                {
                    float offset=i*.05f;
                    robot.transform.position=new Vector3(-5+offset,0,2);
                    cargo.position=cargoPosition+new Vector3(offset,.26f,0);
                    Physics.SyncTransforms();
                    if(moving.Any(a=>obstacles.Any(b=>Physics.ComputePenetration(a,a.transform.position,a.transform.rotation,
                        b,b.transform.position,b.transform.rotation,out _,out float depth) && depth > .0001f)))
                        throw new Exception("Raised side transfer collides at offset "+offset);
                }
                // P2: approach loaded, lower onto the two tracks, then withdraw with platform down.
                for(int phase=0;phase<3;phase++)
                for(int i=0;i<=50;i++)
                {
                    float t=i/50f;
                    float robotX=phase==0?2.5f*(1-t):phase==2?2.5f*t:0;
                    float extension=phase==0?.35f:phase==1?.35f*(1-t):0;
                    robot.transform.position=new Vector3(robotX,0,2);
                    platform.localPosition=new Vector3(0,.69f+extension,0);
                    cargo.position=new Vector3(phase==0?robotX:0,.88f+Mathf.Max(0,extension-.09f),2);
                    Physics.SyncTransforms();
                    if(moving.Any(a=>obstacles.Any(b=>Physics.ComputePenetration(a,a.transform.position,a.transform.rotation,
                        b,b.transform.position,b.transform.rotation,out _,out float depth) && depth > .0001f)))
                        throw new Exception("P2 deposit envelope blocked: phase "+phase+", step "+i);
                }
                var conveyors=scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>())
                    .Where(t=>t.name=="StaticOpenCenterConveyorLift").ToArray();
                if(conveyors.Length!=2 || conveyors.Any(t=>t.GetComponentsInChildren<Rigidbody>().Length>0 ||
                    t.GetComponentsInChildren<Animator>().Length>0 || t.GetComponentsInChildren<MonoBehaviour>().Length>0))
                    throw new Exception("Conveyor must be static geometry only");
            }
            finally
            {
                robot.transform.SetPositionAndRotation(originalPosition,originalRotation);platform.localPosition=originalPlatform;
                cargo.position=cargoPosition;robot.GetComponent<LiftMechanismVisual>().Refresh();Physics.SyncTransforms();
            }
            Debug.Log("RACK_PASSAGES_OK: 61 longitudinal samples, low entry blocks raised robot, 36 pickup lift samples, 51 raised lateral-transfer samples");
            Debug.Log("CONVEYOR_DEPOSIT_OK: P2 loaded approach, lowering, empty withdrawal; 153 poses; two static conveyors");
            foreach(float z in new[]{1.36f,2.64f})
                if(!Physics.Raycast(new Vector3(1.0f,1.1f,z),Vector3.down,out var contact,.5f) || Mathf.Abs(contact.point.y-.82f)>.0001f)
                    throw new Exception("Missing conveyor load-bearing contact at 0.82 m");
            Debug.Log("CONVEYOR_SUPPORT_OK: both static track contact surfaces at 0.82 m");
        }

        private static void RenderRackDetails(Camera camera,GameObject robot)
        {
            var cp=camera.transform.position;var cr=camera.transform.rotation;float size=camera.orthographicSize;
            var rp=robot.transform.position;var platform=robot.transform.Find("LiftPlatform");var lp=platform.localPosition;
            robot.transform.position=new Vector3(-5,0,1.1f);
            camera.transform.position=new Vector3(7,7,-12);camera.transform.LookAt(new Vector3(0,1,2));camera.orthographicSize=7.5f;
            RenderPreview(camera,"racks-overview.png");
            camera.transform.position=new Vector3(-1.2f,2.4f,-3.5f);camera.transform.LookAt(new Vector3(-5,1.0f,2));camera.orthographicSize=2.8f;
            RenderPreview(camera,"rack-pickup.png");
            robot.transform.position=new Vector3(5,0,1.7f);platform.localPosition=new Vector3(0,1.04f,0);
            robot.GetComponent<LiftMechanismVisual>().Refresh();
            camera.transform.position=new Vector3(7,2.7f,-4);camera.transform.LookAt(new Vector3(5,1.2f,2));
            RenderPreview(camera,"rack-high.png");
            // Static pose illustration of the payload envelope, not an automatic attachment demo.
            var cargo=robot.scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>()).Single(t=>t.name=="PickupCargo");
            var cargoPosition=cargo.position;cargo.position=new Vector3(5,1.14f,1.7f);
            RenderPreview(camera,"rack-high-loaded.png");cargo.position=cargoPosition;
            // Inspection cutaway: hide surrounding rack visuals only for these two images.
            var station=robot.scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Transform>())
                .Single(t=>t.name=="P2_DROPOFF_RACK").Find("StaticOpenCenterConveyorLift");
            var hidden=robot.scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Renderer>())
                .Where(r=>r.enabled && !r.transform.IsChildOf(robot.transform) && !r.transform.IsChildOf(station) &&
                    !r.transform.IsChildOf(cargo) && r.name!="Floor").ToArray();
            foreach(var r in hidden) r.enabled=false;
            var rr=robot.transform.rotation;robot.transform.rotation=Quaternion.Euler(0,90,0);
            robot.transform.position=new Vector3(0,0,2);platform.localPosition=lp;robot.GetComponent<LiftMechanismVisual>().Refresh();
            camera.transform.position=new Vector3(3.6f,2.7f,-.8f);camera.transform.LookAt(new Vector3(0,.65f,2));camera.orthographicSize=1.95f;
            RenderPreview(camera,"conveyor-open-center.png");
            cargo.position=new Vector3(0,.88f,2);
            RenderPreview(camera,"conveyor-deposited.png");cargo.position=cargoPosition;
            foreach(var r in hidden) r.enabled=true;
            robot.transform.rotation=rr;
            robot.transform.position=rp;platform.localPosition=lp;robot.GetComponent<LiftMechanismVisual>().Refresh();
            camera.transform.SetPositionAndRotation(cp,cr);camera.orthographicSize=size;
        }
        private static void RenderPreview(Camera camera,string filename="warehouse.png")
        {
            Directory.CreateDirectory("WarehouseValidation");
            var rt=new RenderTexture(1600,1100,24);var previous=RenderTexture.active;
            camera.targetTexture=rt;camera.Render();RenderTexture.active=rt;
            var texture=new Texture2D(1600,1100,TextureFormat.RGB24,false);
            texture.ReadPixels(new Rect(0,0,1600,1100),0,0);texture.Apply();
            File.WriteAllBytes("WarehouseValidation/"+filename,texture.EncodeToPNG());
            camera.targetTexture=null;RenderTexture.active=previous;
            UnityEngine.Object.DestroyImmediate(texture);rt.Release();UnityEngine.Object.DestroyImmediate(rt);
        }
    }
}

