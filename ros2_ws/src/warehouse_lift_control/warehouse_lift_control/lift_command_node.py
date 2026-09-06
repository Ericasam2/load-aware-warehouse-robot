#!/usr/bin/env python3

import math

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from rclpy.parameter import Parameter
from std_msgs.msg import Bool, Float32


class LiftCommandNode(Node):
    """Publish a lift target and verify Unity position feedback."""

    MINIMUM_HEIGHT = 0.0
    MAXIMUM_HEIGHT = 0.35

    def __init__(self) -> None:
        super().__init__("lift_command_node")

        self.declare_parameter("target_height", 0.0)
        self.declare_parameter("publish_rate", 10.0)
        self.declare_parameter("position_tolerance", 0.005)

        self._target_height = self._validated_height(
            self.get_parameter("target_height").value
        )
        publish_rate = max(1.0, float(self.get_parameter("publish_rate").value))
        self._position_tolerance = max(
            0.0001, float(self.get_parameter("position_tolerance").value)
        )
        self._last_state = math.nan
        self._unity_reports_at_target = False
        self._reported_reached = False

        self._command_publisher = self.create_publisher(
            Float32, "/lift/command", 10
        )
        self.create_subscription(Float32, "/lift/state", self._state_callback, 10)
        self.create_subscription(Bool, "/lift/at_target", self._target_callback, 10)
        self.create_timer(1.0 / publish_rate, self._publish_command)
        self.add_on_set_parameters_callback(self._parameter_callback)

        self.get_logger().info(
            f"Lift command loop started; target={self._target_height:.3f} m"
        )

    def _validated_height(self, value: object) -> float:
        height = float(value)
        if not self.MINIMUM_HEIGHT <= height <= self.MAXIMUM_HEIGHT:
            raise ValueError(
                f"target_height must be in "
                f"[{self.MINIMUM_HEIGHT:.2f}, {self.MAXIMUM_HEIGHT:.2f}] m"
            )
        return height

    def _publish_command(self) -> None:
        message = Float32()
        message.data = self._target_height
        self._command_publisher.publish(message)

    def _state_callback(self, message: Float32) -> None:
        self._last_state = float(message.data)
        self._check_target_reached()

    def _target_callback(self, message: Bool) -> None:
        self._unity_reports_at_target = bool(message.data)
        self._check_target_reached()

    def _check_target_reached(self) -> None:
        state_is_valid = not math.isnan(self._last_state)
        within_tolerance = (
            state_is_valid
            and abs(self._last_state - self._target_height)
            <= self._position_tolerance
        )
        reached = within_tolerance and self._unity_reports_at_target

        if reached and not self._reported_reached:
            self.get_logger().info(
                f"Lift reached {self._last_state:.3f} m "
                f"(target {self._target_height:.3f} m)"
            )
        self._reported_reached = reached

    def _parameter_callback(self, parameters: list[Parameter]) -> SetParametersResult:
        for parameter in parameters:
            if parameter.name != "target_height":
                continue

            try:
                requested_height = self._validated_height(parameter.value)
            except (TypeError, ValueError) as error:
                return SetParametersResult(successful=False, reason=str(error))

            self._target_height = requested_height
            self._reported_reached = False
            self.get_logger().info(
                f"New lift target accepted: {self._target_height:.3f} m"
            )

        return SetParametersResult(successful=True)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = LiftCommandNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
