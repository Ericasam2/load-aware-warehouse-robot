using RosMessageTypes.BuiltinInterfaces;
using RosMessageTypes.Geometry;
using RosMessageTypes.Nav;
using RosMessageTypes.Std;
using Unity.Robotics.ROSTCPConnector;
using UnityEngine;

namespace WarehouseRobot
{
    /// <summary>
    /// ROS 2 differential-drive controller backed by two physical WheelColliders.
    ///
    /// ROS FLU coordinates are converted to Unity RUF coordinates:
    /// ROS +x -> Unity +z, ROS +y -> Unity -x, ROS +z -> Unity +y.
    /// </summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Rigidbody))]
    public sealed class RosDifferentialDrive : MonoBehaviour
    {
        [Header("Physical wheel model")]
        [SerializeField] private WheelCollider leftWheelCollider;
        [SerializeField] private WheelCollider rightWheelCollider;
        [SerializeField] private Transform leftWheelVisual;
        [SerializeField] private Transform rightWheelVisual;
        [SerializeField] private float wheelRadius = 0.18f;
        [SerializeField] private float trackWidth = 0.78f;

        [Header("Wheel-speed control")]
        [SerializeField] private float wheelSpeedGain = 8.0f;
        [SerializeField] private float maximumMotorTorque = 45.0f;
        [SerializeField] private float holdingBrakeTorque = 80.0f;
        [SerializeField] private float stoppedSpeedTolerance = 0.01f;

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

        private static readonly Quaternion CylinderToWheelRotation =
            Quaternion.Euler(0.0f, 0.0f, 90.0f);

        private Rigidbody robotBody;
        private ROSConnection ros;
        private float commandedLinear;
        private float commandedAngular;
        private float lastCommandTime = float.NegativeInfinity;
        private float nextOdomPublishTime;
        private Vector3 startPosition;
        private Quaternion startRotation;

        /// <summary>
        /// Connects the scene-generated physical wheels to this controller.
        /// </summary>
        public void Configure(
            WheelCollider leftCollider,
            WheelCollider rightCollider,
            Transform leftVisual,
            Transform rightVisual,
            float radius,
            float separation)
        {
            leftWheelCollider = leftCollider;
            rightWheelCollider = rightCollider;
            leftWheelVisual = leftVisual;
            rightWheelVisual = rightVisual;
            wheelRadius = radius;
            trackWidth = separation;
        }

        private void Awake()
        {
            robotBody = GetComponent<Rigidbody>();
            robotBody.interpolation = RigidbodyInterpolation.Interpolate;
            robotBody.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            robotBody.constraints = RigidbodyConstraints.FreezeRotationX |
                                    RigidbodyConstraints.FreezeRotationZ;

            if (leftWheelCollider == null || rightWheelCollider == null)
            {
                Debug.LogError(
                    "RosDifferentialDrive requires left and right WheelColliders. " +
                    "Rebuild or upgrade the robot scene from the Warehouse Robotics menu.",
                    this);
                enabled = false;
                return;
            }

            ApplyWheelGeometry(leftWheelCollider);
            ApplyWheelGeometry(rightWheelCollider);
            leftWheelCollider.ConfigureVehicleSubsteps(1.0f, 12, 15);
            rightWheelCollider.ConfigureVehicleSubsteps(1.0f, 12, 15);

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
            bool commandTimedOut = Time.time - lastCommandTime > commandTimeoutSeconds;
            float linear = commandTimedOut ? 0.0f : commandedLinear;
            float angular = commandTimedOut ? 0.0f : commandedAngular;

            // Differential-drive inverse kinematics in the ROS base frame.
            float halfTrack = trackWidth * 0.5f;
            float leftTargetAngularSpeed = (linear - angular * halfTrack) / wheelRadius;
            float rightTargetAngularSpeed = (linear + angular * halfTrack) / wheelRadius;

            DriveWheel(leftWheelCollider, leftTargetAngularSpeed);
            DriveWheel(rightWheelCollider, rightTargetAngularSpeed);
            UpdateWheelVisual(leftWheelCollider, leftWheelVisual);
            UpdateWheelVisual(rightWheelCollider, rightWheelVisual);

            if (Time.time >= nextOdomPublishTime)
            {
                PublishOdometry();
                nextOdomPublishTime = Time.time + 1.0f / Mathf.Max(1.0f, odomPublishRateHz);
            }
        }

        private void DriveWheel(WheelCollider wheel, float targetAngularSpeed)
        {
            if (Mathf.Abs(targetAngularSpeed) <= stoppedSpeedTolerance)
            {
                wheel.motorTorque = 0.0f;
                wheel.brakeTorque = holdingBrakeTorque;
                return;
            }

            float measuredAngularSpeed = wheel.rpm * 2.0f * Mathf.PI / 60.0f;
            float speedError = targetAngularSpeed - measuredAngularSpeed;
            wheel.brakeTorque = 0.0f;
            wheel.motorTorque = Mathf.Clamp(
                wheelSpeedGain * speedError,
                -maximumMotorTorque,
                maximumMotorTorque);
        }

        private void UpdateWheelVisual(WheelCollider wheel, Transform visual)
        {
            if (visual == null)
            {
                return;
            }

            wheel.GetWorldPose(out Vector3 wheelPosition, out Quaternion wheelRotation);
            visual.SetPositionAndRotation(
                wheelPosition,
                wheelRotation * CylinderToWheelRotation);
        }

        private void ApplyWheelGeometry(WheelCollider wheel)
        {
            wheel.radius = wheelRadius;
            wheel.mass = 2.0f;
            wheel.wheelDampingRate = 0.5f;
            wheel.suspensionDistance = 0.05f;
            wheel.forceAppPointDistance = 0.08f;

            JointSpring spring = wheel.suspensionSpring;
            spring.spring = 8000.0f;
            spring.damper = 1000.0f;
            spring.targetPosition = 0.5f;
            wheel.suspensionSpring = spring;

            WheelFrictionCurve forwardFriction = wheel.forwardFriction;
            forwardFriction.extremumSlip = 0.4f;
            forwardFriction.extremumValue = 1.0f;
            forwardFriction.asymptoteSlip = 0.8f;
            forwardFriction.asymptoteValue = 0.5f;
            forwardFriction.stiffness = 1.5f;
            wheel.forwardFriction = forwardFriction;

            WheelFrictionCurve sidewaysFriction = wheel.sidewaysFriction;
            sidewaysFriction.extremumSlip = 0.2f;
            sidewaysFriction.extremumValue = 1.0f;
            sidewaysFriction.asymptoteSlip = 0.5f;
            sidewaysFriction.asymptoteValue = 0.75f;
            sidewaysFriction.stiffness = 2.0f;
            wheel.sidewaysFriction = sidewaysFriction;
        }

        private void PublishOdometry()
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

            Vector3 localVelocity = transform.InverseTransformDirection(robotBody.linearVelocity);
            float measuredLinear = localVelocity.z;
            float measuredAngular = -robotBody.angularVelocity.y;
            var velocity = new TwistMsg(
                new Vector3Msg(measuredLinear, 0.0, 0.0),
                new Vector3Msg(0.0, 0.0, measuredAngular));

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

        private void OnDisable()
        {
            StopWheel(leftWheelCollider);
            StopWheel(rightWheelCollider);
        }

        private static void StopWheel(WheelCollider wheel)
        {
            if (wheel == null)
            {
                return;
            }

            wheel.motorTorque = 0.0f;
            wheel.brakeTorque = 0.0f;
        }

        private void OnValidate()
        {
            wheelRadius = Mathf.Max(0.01f, wheelRadius);
            trackWidth = Mathf.Max(0.05f, trackWidth);
            wheelSpeedGain = Mathf.Max(0.0f, wheelSpeedGain);
            maximumMotorTorque = Mathf.Max(0.0f, maximumMotorTorque);
            holdingBrakeTorque = Mathf.Max(0.0f, holdingBrakeTorque);
            stoppedSpeedTolerance = Mathf.Max(0.0f, stoppedSpeedTolerance);
            maxLinearSpeed = Mathf.Max(0.0f, maxLinearSpeed);
            maxAngularSpeed = Mathf.Max(0.0f, maxAngularSpeed);
            commandTimeoutSeconds = Mathf.Max(0.01f, commandTimeoutSeconds);
            odomPublishRateHz = Mathf.Max(1.0f, odomPublishRateHz);
        }
    }
}
