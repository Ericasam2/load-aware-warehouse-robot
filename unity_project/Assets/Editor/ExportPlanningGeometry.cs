using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace WarehouseRobot.Editor
{
    public static class ExportPlanningGeometry
    {
        [Serializable] public class Solid { public string id, name, kind; public float[] min, max; }
        [Serializable] public class Goal { public string id; public float[] pose; }
        [Serializable] public class Snapshot
        {
            public int schema_version=1;
            public string frame="map", scene_path, scene_sha256;
            public string coordinates="map=(unity.z,-unity.x,unity.y); metres; yaw radians CCW";
            public float[] bounds;
            public float[] map_from_odom;
            public float robot_mass_kg, wheel_radius, track_width, lift_max_extension;
            public float[] body_size_forward_left_up, platform_size_forward_left_up;
            public List<Solid> obstacles=new List<Solid>();
            public List<Goal> goals=new List<Goal>();
        }
        [MenuItem("Warehouse Robotics/Export A Star Planning Geometry")]
        public static void Export()
        {
            if(EditorApplication.isPlayingOrWillChangePlaymode) throw new Exception("Exit Play Mode before exporting");
            var scene=UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            if(Application.isBatchMode) scene=EditorSceneManager.OpenScene(BuildWarehouseScene.ScenePath,OpenSceneMode.Single);
            if(scene.path!=BuildWarehouseScene.ScenePath || scene.isDirty)
                throw new Exception("Open and save WarehouseEnvironment before exporting its geometry");
            var roots=scene.GetRootGameObjects();
            var robot=roots.Single(o=>o.GetComponent<RosDifferentialDrive>()!=null);
            if(Quaternion.Angle(robot.transform.rotation,Quaternion.identity)>.01f) throw new Exception("Exporter currently requires initial robot yaw=0");
            var data=new Snapshot {scene_path=scene.path,map_from_odom=new[]{robot.transform.position.z,-robot.transform.position.x,0f}};
            var floor=roots.SelectMany(o=>o.GetComponentsInChildren<Collider>()).Single(c=>c.name=="Floor").bounds;
            if(Mathf.Abs(floor.max.y)>.001f) throw new Exception("Planning layers require floor surface at Unity Y=0");
            data.bounds=new[]{floor.min.z,-floor.max.x,floor.max.z,-floor.min.x};
            var wheels=robot.GetComponentsInChildren<WheelCollider>();
            data.robot_mass_kg=robot.GetComponent<Rigidbody>().mass;
            data.wheel_radius=wheels.First().radius;
            data.track_width=Mathf.Abs(wheels[0].transform.localPosition.x-wheels[1].transform.localPosition.x);
            var body=robot.GetComponent<BoxCollider>().size;
            data.body_size_forward_left_up=new[]{body.z,body.x,body.y};
            var platform=robot.transform.Find("LiftPlatform").GetComponent<BoxCollider>().bounds.size;
            data.platform_size_forward_left_up=new[]{platform.z,platform.x,platform.y};
            data.lift_max_extension=new SerializedObject(robot.GetComponent<RosLiftController>()).FindProperty("maximumExtension").floatValue;
            using(var sha=SHA256.Create()) data.scene_sha256=BitConverter.ToString(sha.ComputeHash(File.ReadAllBytes(scene.path))).Replace("-","").ToLowerInvariant();
            foreach(var c in roots.Where(o=>o!=robot).SelectMany(o=>o.GetComponentsInChildren<Collider>()))
            {
                if(!c.enabled || c.isTrigger || c.name=="Floor" || c.name=="Ground") continue;
                if(!(c is BoxCollider) || Quaternion.Angle(c.transform.rotation,Quaternion.identity)>.01f)
                    throw new Exception("Unsupported planning collider; do not silently flatten: "+c.name);
                var b=c.bounds;string id=PathOf(c.transform);
                data.obstacles.Add(new Solid {id=id,name=c.name,
                    kind=id.Contains("PickupCargo")?"pickup_payload":id.Contains("TemporaryObstacle")?"temporary":"static",
                    min=new[]{b.min.z,-b.max.x,b.min.y},max=new[]{b.max.z,-b.min.x,b.max.y}});
            }
            foreach(string name in new[]{"RobotStart","Pickup_P1","Dropoff_P2","PickupSideExit","LowGate","HighGate"})
            {
                var t=roots.SelectMany(o=>o.GetComponentsInChildren<Transform>()).Single(o=>o.name==name);
                data.goals.Add(new Goal{id=name,pose=new[]{t.position.z,-t.position.x,name=="RobotStart"?0f:-Mathf.PI/2}});
            }
            string directory=System.IO.Path.GetFullPath("../maps");Directory.CreateDirectory(directory);
            File.WriteAllText(System.IO.Path.Combine(directory,"scene_geometry.json"),JsonUtility.ToJson(data,true));
            Debug.Log("PLANNING_EXPORT_OK: "+data.obstacles.Count+" box colliders -> "+directory);
        }
        private static string PathOf(Transform t) => t.parent==null?t.name:PathOf(t.parent)+"/"+t.name+"["+t.GetSiblingIndex()+"]";
    }
}
