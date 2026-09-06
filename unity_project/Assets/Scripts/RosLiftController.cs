using RosMessageTypes.Std;
using Unity.Robotics.ROSTCPConnector;
using UnityEngine;

namespace WarehouseRobot
{
    /// <summary>
    /// Minimal lift position loop for the Unity robot.
    ///
    /// Input:  /lift/command   std_msgs/msg/Float32, target extension in metres.
    /// Output: /lift/state     std_msgs/msg/Float32, measured extension in metres.
    ///         /lift/at_target std_msgs/msg/Bool, true inside the position tolerance.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class RosLiftController : MonoBehaviour
    {
        [Header("Lift model")]
        [SerializeField] private Transform liftPlatform;
        [SerializeField] private float minimumExtension = 0.0f;
        [SerializeField] private float maximumExtension = 0.35f;
        [SerializeField] private float liftSpeed = 0.15f;
        [SerializeField] private float positionTolerance = 0.005f;

        [Header("ROS topics")]
        [SerializeField] private string commandTopic = "/lift/command";
        [SerializeField] private string stateTopic = "/lift/state";
        [SerializeField] private string atTargetTopic = "/lift/at_target";
        [SerializeField] private float statePublishRateHz = 20.0f;

        private ROSConnection ros;
        private Vector3 retractedLocalPosition;
        private float targetExtension;
        private float currentExtension;
        private float nextPublishTime;

        public void Configure(Transform platform)
        {
            liftPlatform = platform;
        }

        private void Awake()
        {
            if (liftPlatform == null)
            {
                Debug.LogError("RosLiftController requires a LiftPlatform transform.", this);
                enabled = false;
                return;
            }

            retractedLocalPosition = liftPlatform.localPosition;
            targetExtension = Mathf.Clamp(0.0f, minimumExtension, maximumExtension);
            currentExtension = targetExtension;
            ApplyLiftPosition();
        }

        private void Start()
        {
            ros = ROSConnection.GetOrCreateInstance();
            ros.Subscribe<Float32Msg>(commandTopic, ReceiveLiftCommand);
            ros.RegisterPublisher<Float32Msg>(stateTopic);
            ros.RegisterPublisher<BoolMsg>(atTargetTopic);
            PublishState();
        }

        private void ReceiveLiftCommand(Float32Msg message)
        {
            targetExtension = Mathf.Clamp(message.data, minimumExtension, maximumExtension);
            Debug.Log($"Lift target set to {targetExtension:F3} m", this);
        }

        private void FixedUpdate()
        {
            currentExtension = Mathf.MoveTowards(
                currentExtension,
                targetExtension,
                liftSpeed * Time.fixedDeltaTime);

            ApplyLiftPosition();

            if (Time.time >= nextPublishTime)
            {
                PublishState();
                nextPublishTime = Time.time + 1.0f / Mathf.Max(1.0f, statePublishRateHz);
            }
        }

        private void ApplyLiftPosition()
        {
            liftPlatform.localPosition = retractedLocalPosition + Vector3.up * currentExtension;
        }

        private void PublishState()
        {
            if (ros == null)
            {
                return;
            }

            bool atTarget = Mathf.Abs(currentExtension - targetExtension) <= positionTolerance;
            ros.Publish(stateTopic, new Float32Msg(currentExtension));
            ros.Publish(atTargetTopic, new BoolMsg(atTarget));
        }

        private void OnValidate()
        {
            maximumExtension = Mathf.Max(minimumExtension, maximumExtension);
            liftSpeed = Mathf.Max(0.001f, liftSpeed);
            positionTolerance = Mathf.Max(0.0001f, positionTolerance);
            statePublishRateHz = Mathf.Max(1.0f, statePublishRateHz);
        }
    }
}
