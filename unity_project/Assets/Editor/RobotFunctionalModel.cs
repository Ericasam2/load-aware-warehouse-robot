using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace WarehouseRobot.Editor
{
    /// <summary>Functional visual assembly. Existing chassis/platform colliders and ROS controls remain authoritative.</summary>
    public static class RobotFunctionalModel
    {
        private static Material shell, dark, metal, orange, white;

        [MenuItem("Warehouse Robotics/Optimize Current Robot Model")]
        public static void UpgradeCurrent()
        {
            if (EditorApplication.isPlayingOrWillChangePlaymode) return;
            var robot = UnityEngine.SceneManagement.SceneManager.GetActiveScene().GetRootGameObjects()
                .FirstOrDefault(o => o.GetComponent<RosDifferentialDrive>() != null);
            if (robot == null) { Debug.LogError("No ROS robot in active scene."); return; }
            BuildMinimalRobotScene.UpgradeRobot(robot);
        }

        public static void Apply(GameObject robot)
        {
            var platform = robot.transform.Find("LiftPlatform");
            if (platform == null) throw new InvalidOperationException("Robot requires the existing LiftPlatform.");
            shell = Material("Shell", new Color(.08f,.27f,.43f));
            dark = Material("Rubber", new Color(.035f,.045f,.055f));
            metal = Material("Metal", new Color(.55f,.63f,.68f));
            orange = Material("LiftSafety", new Color(.96f,.57f,.08f));
            white = Material("Marking", new Color(.88f,.94f,.98f));
            ReplaceGroup(robot.transform,"FunctionalBody");
            ReplaceGroup(platform,"ContactSurface");
            var body = robot.transform.Find("FunctionalBody");
            robot.transform.Find("Chassis").GetComponent<Renderer>().enabled = false;
            robot.transform.Find("LiftColumn").GetComponent<Renderer>().enabled = false;
            robot.transform.Find("ForwardMarker").GetComponent<Renderer>().enabled = false;

            // All panels stay inside the established 0.70 x 0.28 x 0.90 m body collider.
            Box(body,"LowerTray",new Vector3(0,.215f,0),new Vector3(.70f,.07f,.90f),dark);
            Box(body,"BatteryAndDriveHousing",new Vector3(0,.335f,0),new Vector3(.66f,.17f,.84f),shell);
            Box(body,"ServiceDeck",new Vector3(0,.44f,0),new Vector3(.70f,.04f,.90f),metal);
            foreach(float sign in new[]{-1f,1f})
            {
                Box(body,"EndBumper",new Vector3(0,.30f,sign*.432f),new Vector3(.70f,.085f,.036f),dark);
                Box(body,"EndReflector",new Vector3(sign*.255f,.355f,.424f),new Vector3(.11f,.022f,.006f),white);
                Box(body,"ServiceRail",new Vector3(sign*.325f,.40f,0),new Vector3(.035f,.04f,.82f),shell);
                for(int i=0;i<5;i++)
                    Box(body,"Vent",new Vector3(sign*.332f,.32f,-.27f+i*.033f),new Vector3(.005f,.05f,.012f),dark);
            }
            // Flush arrow points along Unity +Z / ROS +X and stays below the lift contact plane.
            Box(body,"ForwardArrowStem",new Vector3(0,.462f,.39f),new Vector3(.025f,.002f,.06f),orange);
            foreach(float sign in new[]{-1f,1f})
            {
                var arrow=Box(body,"ForwardArrowHead",new Vector3(sign*.018f,.462f,.411f),new Vector3(.012f,.002f,.054f),orange);
                arrow.localRotation=Quaternion.Euler(0,sign*-45,0);
            }
            Label(body,"AGV 01",new Vector3(0,.382f,.426f),Quaternion.Euler(0,180,0),.009f);

            var sleeves = new List<Transform>();
            foreach(float side in new[]{-1f,1f})
            {
                Box(body,"LiftFoot",new Vector3(side*.20f,.475f,0),new Vector3(.18f,.03f,.23f),dark);
                Box(body,"LiftOuterHousing",new Vector3(side*.20f,.555f,0),new Vector3(.14f,.19f,.18f),shell);
                for(int stage=0;stage<3;stage++)
                {
                    float width=.105f-stage*.03f;
                    sleeves.Add(Box(body,"LiftSleeve_"+(side<0?"L":"R")+"_"+(stage+1),
                        new Vector3(side*.20f,.555f,0),new Vector3(width,.19f,width+.025f),stage==1?dark:metal));
                }
            }
            platform.GetComponent<Renderer>().sharedMaterial=orange;
            // Compensate the scaled legacy platform; 2 mm visual overlay avoids coplanar flicker.
            var contact = platform.Find("ContactSurface");
            contact.localScale=new Vector3(1/.62f,1/.08f,1/.72f);
            foreach(float side in new[]{-1f,1f})
                Box(contact,"LoadContactPad",new Vector3(side*.20f,.038f,0),new Vector3(.15f,.008f,.60f),dark);
            Label(contact,"LIFT / 350 mm",new Vector3(0,.042f,0),Quaternion.Euler(90,180,0),.008f);
            var motion = robot.GetComponent<LiftMechanismVisual>() ?? Undo.AddComponent<LiftMechanismVisual>(robot);
            motion.Configure(platform,sleeves.ToArray());
            foreach(string wheelName in new[]{"LeftWheel","RightWheel"})
            {
                var wheel=robot.transform.Find(wheelName);
                wheel.localScale=new Vector3(.36f,.08f,.36f); // Unity cylinder radius is 0.5, height is 2.
                wheel.GetComponent<Renderer>().sharedMaterial=dark;
                ReplaceGroup(wheel,"WheelDetail");
                var detail=wheel.Find("WheelDetail");
                foreach(float face in new[]{-1f,1f})
                {
                    Part(detail,"Hub",PrimitiveType.Cylinder,new Vector3(0,face*1.015f,0),new Vector3(.66f,.06f,.66f),metal);
                    Part(detail,"AxleCap",PrimitiveType.Cylinder,new Vector3(0,face*1.08f,0),new Vector3(.22f,.02f,.22f),shell);
                    // Asymmetric index makes wheel rotation and left/right speed differences visible.
                    Box(detail,"RotationIndex",new Vector3(.19f,face*1.09f,0),new Vector3(.20f,.012f,.065f),orange);
                }
            }
            EditorUtility.SetDirty(motion);
            EditorSceneManager.MarkSceneDirty(robot.scene);
        }

        private static void ReplaceGroup(Transform parent,string name)
        {
            var old=parent.Find(name);
            if(old!=null) Undo.DestroyObjectImmediate(old.gameObject);
            var o=new GameObject(name);Undo.RegisterCreatedObjectUndo(o,"Robot functional model");
            o.transform.SetParent(parent,false);
        }
        private static Transform Box(Transform parent,string name,Vector3 p,Vector3 size,Material mat)
            => Part(parent,name,PrimitiveType.Cube,p,size,mat);
        private static Transform Part(Transform parent,string name,PrimitiveType type,Vector3 p,Vector3 size,Material mat)
        {
            var o=GameObject.CreatePrimitive(type);o.name=name;o.transform.SetParent(parent,false);
            o.transform.localPosition=p;o.transform.localScale=size;
            UnityEngine.Object.DestroyImmediate(o.GetComponent<Collider>());
            o.GetComponent<Renderer>().sharedMaterial=mat;return o.transform;
        }
        private static void Label(Transform parent,string text,Vector3 p,Quaternion rotation,float size)
        {
            var o=new GameObject(text);o.transform.SetParent(parent,false);o.transform.localPosition=p;o.transform.localRotation=rotation;
            var t=o.AddComponent<TextMesh>();t.text=text;t.fontSize=64;t.characterSize=size;t.anchor=TextAnchor.MiddleCenter;t.color=Color.white;
        }
        private static Material Material(string name,Color color)
        {
            const string folder="Assets/Materials/FunctionalRobot";
            if(!AssetDatabase.IsValidFolder(folder)) AssetDatabase.CreateFolder("Assets/Materials","FunctionalRobot");
            string path=folder+"/"+name+".mat";
            var m=AssetDatabase.LoadAssetAtPath<Material>(path);
            if(m==null){m=new Material(Shader.Find("Standard"));AssetDatabase.CreateAsset(m,path);}
            m.color=color;m.SetFloat("_Glossiness",.25f);return m;
        }

        /// <summary>Updates saved scenes in place, preserving their warehouse layout and camera settings.</summary>
        public static void UpgradeSavedScenes()
        {
            if(!Application.isBatchMode) throw new InvalidOperationException("Use the current-scene menu in the interactive editor.");
            foreach(string path in new[]{"Assets/Scenes/MinimalRosRobot.unity",BuildWarehouseScene.ScenePath})
            {
                var scene=EditorSceneManager.OpenScene(path,OpenSceneMode.Single);
                var robot=scene.GetRootGameObjects().Single(o=>o.GetComponent<RosDifferentialDrive>()!=null);
                BuildMinimalRobotScene.UpgradeRobot(robot);
                Validate(robot);
                // Applying again must neither accumulate visuals nor add colliders.
                int before=robot.GetComponentsInChildren<Transform>(true).Length;
                Apply(robot);
                if(before!=robot.GetComponentsInChildren<Transform>(true).Length) throw new Exception("Non-idempotent model upgrade");
                Validate(robot);
                if(path==BuildWarehouseScene.ScenePath) ValidateWarehouseFit(robot);
                EditorSceneManager.SaveScene(scene,path);
                if(path.Contains("Minimal"))
                {
                    Directory.CreateDirectory("WarehouseValidation");
                    RenderRobot(robot,0,"robot-retracted.png");
                    RenderRobot(robot,.35f,"robot-extended.png");
                    robot.transform.Find("LiftPlatform").localPosition=new Vector3(0,.69f,0);
                    robot.GetComponent<LiftMechanismVisual>().Refresh();
                }
            }
            AssetDatabase.SaveAssets();
            Debug.Log("ROBOT_MODEL_BUILD_OK: both scenes, wheel diameter, full lift stroke, collider count, idempotency");
        }

        private static void Validate(GameObject robot)
        {
            var wheels=robot.GetComponentsInChildren<WheelCollider>();
            if(wheels.Length!=2) throw new Exception("Expected two drive wheels");
            if(robot.GetComponentsInChildren<Collider>().Count(c=>c.enabled)!=4)
                throw new Exception("Expected body, platform and two wheel colliders only");
            foreach(var wheel in wheels)
            {
                var visual=robot.transform.Find(wheel.name.Replace("Collider",""));
                if(Mathf.Abs(visual.localScale.x*.5f-wheel.radius)>.0001f) throw new Exception("Visual/physical radius mismatch");
            }
            var platform=robot.transform.Find("LiftPlatform");
            var initial=platform.localPosition;
            for(int step=0;step<=7;step++)
            {
                float extension=step*.05f;
                platform.localPosition=new Vector3(0,.69f+extension,0);
                robot.GetComponent<LiftMechanismVisual>().Refresh();
                foreach(var side in new[]{"L","R"})
                {
                    var top=robot.transform.Find("FunctionalBody/LiftSleeve_"+side+"_3");
                    if(Mathf.Abs(top.localPosition.y+.095f-(platform.localPosition.y-.04f))>.001f)
                        throw new Exception("Lift sleeve detached from platform");
                    for(int i=1;i<3;i++)
                    {
                        var a=robot.transform.Find("FunctionalBody/LiftSleeve_"+side+"_"+i);
                        var b=robot.transform.Find("FunctionalBody/LiftSleeve_"+side+"_"+(i+1));
                        if(a.localPosition.y+.095f < b.localPosition.y-.095f) throw new Exception("Lift sleeve gap");
                    }
                }
            }
            platform.localPosition=initial;robot.GetComponent<LiftMechanismVisual>().Refresh();
            Debug.Log("ROBOT_MODEL_VALIDATION_OK: "+robot.scene.name);
        }

        private static void RenderRobot(GameObject robot,float extension,string filename)
        {
            var platform=robot.transform.Find("LiftPlatform");platform.localPosition=new Vector3(0,.69f+extension,0);
            robot.GetComponent<LiftMechanismVisual>().Refresh();
            var cameraObject=new GameObject("ModelPreviewCamera");var cam=cameraObject.AddComponent<Camera>();
            cam.transform.position=robot.transform.position+new Vector3(1.65f,1.65f,2.1f);
            cam.transform.LookAt(robot.transform.position+Vector3.up*.52f);cam.orthographic=true;cam.orthographicSize=.85f;
            cam.clearFlags=CameraClearFlags.SolidColor;cam.backgroundColor=new Color(.07f,.09f,.12f);
            RenderSettings.ambientMode=UnityEngine.Rendering.AmbientMode.Flat;RenderSettings.ambientLight=new Color(.25f,.28f,.32f);
            foreach(var light in robot.scene.GetRootGameObjects().SelectMany(o=>o.GetComponentsInChildren<Light>())) light.intensity=.9f;
            var rt=new RenderTexture(1200,1100,24);var previous=RenderTexture.active;cam.targetTexture=rt;cam.Render();RenderTexture.active=rt;
            var texture=new Texture2D(1200,1100,TextureFormat.RGB24,false);texture.ReadPixels(new Rect(0,0,1200,1100),0,0);texture.Apply();
            File.WriteAllBytes("WarehouseValidation/"+filename,texture.EncodeToPNG());RenderTexture.active=previous;cam.targetTexture=null;
            UnityEngine.Object.DestroyImmediate(texture);rt.Release();UnityEngine.Object.DestroyImmediate(rt);UnityEngine.Object.DestroyImmediate(cameraObject);
        }

        private static void ValidateWarehouseFit(GameObject robot)
        {
            BuildWarehouseScene.ValidateRackPassages(robot.scene, robot);
        }
    }
}
