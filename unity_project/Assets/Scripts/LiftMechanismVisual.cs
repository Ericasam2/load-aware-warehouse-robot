using UnityEngine;

namespace WarehouseRobot
{
    /// <summary>Visual telescoping sleeves driven by the existing lift platform, in metres.
    /// No independent actuator, physics joint, sensor or load-state simulation.</summary>
    [ExecuteAlways, DisallowMultipleComponent]
    public sealed class LiftMechanismVisual : MonoBehaviour
    {
        [SerializeField] private Transform platform;
        [SerializeField] private Transform[] sleeves;
        [SerializeField] private Vector3[] retractedPositions;
        [SerializeField] private float retractedPlatformHeight = .69f;

        public void Configure(Transform liftPlatform, Transform[] stages)
        {
            platform = liftPlatform;
            sleeves = stages;
            retractedPlatformHeight = platform.localPosition.y;
            retractedPositions = new Vector3[stages.Length];
            for (int i = 0; i < stages.Length; i++) retractedPositions[i] = stages[i].localPosition;
            Refresh();
        }

        private void LateUpdate() => Refresh();

        public void Refresh()
        {
            if (platform == null || sleeves == null || retractedPositions == null ||
                sleeves.Length != retractedPositions.Length) return;
            float extension = Mathf.Clamp(platform.localPosition.y - retractedPlatformHeight, 0, .35f);
            for (int i = 0; i < sleeves.Length; i++)
                if (sleeves[i] != null)
                    sleeves[i].localPosition = retractedPositions[i] + Vector3.up * (extension * ((i % 3 + 1) / 3f));
        }
    }
}
