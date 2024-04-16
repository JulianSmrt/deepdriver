from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription(
        [
            Node(
                package="lane_detection_pkg",
                namespace="lane_detection_pkg",
                executable="lane_detection_node",
                name="lane_detection_node",
                parameters=[{"PUBLISH_DISPLAY_OUTPUT": True}],
            )
        ]