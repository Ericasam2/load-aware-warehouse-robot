using RosMessageTypes.Geometry;
using RosMessageTypes.Nav;
using RosMessageTypes.Std;
using RosMessageTypes.BuiltinInterfaces;
using Unity.Robotics.ROSTCPConnector;
using UnityEngine;

namespace WarehouseRobot
{
    /// <summary>
    /// Minimal ROS 2 differential-drive smoke test.
    ///
    /// ROS FLU coordinates are converted to Unity RUF coordinates:
    /// ROS +x -> Unity +z, ROS +y -> Unity -x, ROS +z -> Unity +y.
    /// The first milestone intentionally uses a kinematic Rigidbody controller.
    /// Wheel dynamics can be added after ROS communication is proven stable.
    /// </summary>
    [RequireComponent(typeof(Rigidbody))]
    public sealed class RosDifferentialDrive : MonoBehaviour
    {
        [Header("ROS topics")]
        [SerializeField] private string cmdVelTopic = "/cmd_vel";
        [SerializeField] private string odomTopic = "/odom";

        [Header("Motion limits")]
        [SerializeField] private float maxLinearSpeed = 1.0f;
        [SerializeField] private float maxAngularSpeed = 1.5f;
        [SerializeField] private float commandTimeoutSeconds = 0.5f;

        [Header("Odometry")]
        [SerializeField] private string odomFrame = "odom";
        [SerializeField] private string baseFrame = "base_link";
        [SerializeField] private float odomPublishRateHz = 20.0f;

        private Rigidbody robotBody;
        private ROSConnection ros;
        private float commandedLinear;
        private float commandedAngular;
        private float lastCommandTime = float.NegativeInfinity;
        private float nextOdomPublishTime;
        private Vector3 startPosition;
        private Quaternion startRotation;

        private void Awake()
        {
            robotBody = GetComponent<Rigidbody>();
            robotBody.interpolation = RigidbodyInterpolation.Interpolate;
            robotBody.constraints = RigidbodyConstraints.FreezeRotationX |
                                    RigidbodyConstraints.FreezeRotationZ;

            startPosition = transform.position;
            startRotation = transform.rotation;
        }

        private void Start()
        {
            ros = ROSConnection.GetOrCreateInstance();
            ros.Subscribe<TwistMsg>(cmdVelTopic, ReceiveVelocityCommand);
            ros.RegisterPublisher<OdometryMsg>(odomTopic);
        }

        private void ReceiveVelocityCommand(TwistMsg message)
        {
            commandedLinear = Mathf.Clamp((float)message.linear.x, -maxLinearSpeed, maxLinearSpeed);
            commandedAngular = Mathf.Clamp((float)message.angular.z, -maxAngularSpeed, maxAngularSpeed);
            lastCommandTime = Time.time;
        }

        private void FixedUpdate()
        {
            float linear = commandedLinear;
            float angular = commandedAngular;

            if (Time.time - lastCommandTime > commandTimeoutSeconds)
            {
                linear = 0.0f;
                angular = 0.0f;
            }

            float dt = Time.fixedDeltaTime;
            Quaternion yawStep = Quaternion.Euler(0.0f, -angular * Mathf.Rad2Deg * dt, 0.0f);
            robotBody.MoveRotation(robotBody.rotation * yawStep);
            robotBody.MovePosition(robotBody.position + transform.forward * (linear * dt));

            if (Time.time >= nextOdomPublishTime)
            {
                PublishOdometry(linear, angular);
                nextOdomPublishTime = Time.time + 1.0f / Mathf.Max(1.0f, odomPublishRateHz);
            }
        }

        private void PublishOdometry(float linear, float angular)
        {
            Vector3 relativePosition = Quaternion.Inverse(startRotation) * (transform.position - startPosition);
            Quaternion relativeRotation = Quaternion.Inverse(startRotation) * transform.rotation;

            // Unity yaw is clockwise relative to ROS yaw under the RUF <-> FLU conversion.
            float rosYaw = -relativeRotation.eulerAngles.y * Mathf.Deg2Rad;
            rosYaw = Mathf.Atan2(Mathf.Sin(rosYaw), Mathf.Cos(rosYaw));

            double halfYaw = rosYaw * 0.5;
            var orientation = new QuaternionMsg(
                0.0,
                0.0,
                System.Math.Sin(halfYaw),
                System.Math.Cos(halfYaw));

            var pose = new PoseMsg(
                new PointMsg(relativePosition.z, -relativePosition.x, relativePosition.y),
                orientation);

            var velocity = new TwistMsg(
                new Vector3Msg(linear, 0.0, 0.0),
                new Vector3Msg(0.0, 0.0, angular));

            double now = Time.realtimeSinceStartupAsDouble;
            int seconds = (int)now;
            uint nanoseconds = (uint)((now - seconds) * 1_000_000_000.0);

            // The Connector compiles different Header/Time constructors before and
            // after ROS2 is selected in Robotics > ROS Settings. Keeping both
            // branches valid lets a fresh project compile before that first setup.
#if ROS2
            var stamp = new TimeMsg(seconds, nanoseconds);
            var header = new HeaderMsg(stamp, odomFrame);
#else
            var stamp = new TimeMsg((uint)seconds, nanoseconds);
            var header = new HeaderMsg(0u, stamp, odomFrame);
#endif

            var message = new OdometryMsg(
                header,
                baseFrame,
                new PoseWithCovarianceMsg(pose, new double[36]),
                new TwistWithCovarianceMsg(velocity, new double[36]));

            ros.Publish(odomTopic, message);
        }
    }
}
