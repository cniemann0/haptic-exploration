import rospy
import actionlib
import numpy as np

from typing import Iterator, Tuple
from haptic_exploration.util import Pose
from mujoco_ros_msgs.msg import StepAction, StepGoal, MocapState
from mujoco_ros_msgs.srv import SetBodyState, SetBodyStateRequest, GetBodyState, GetBodyStateRequest, GetBodyStateResponse
from tactile_msgs.msg import TactileState
from std_srvs.srv import Empty


class MujocoRosClient:

    def __init__(self, node_name) -> None:
        rospy.init_node(node_name)

        rospy.Subscriber("/tactile_module_16x16_v2", TactileState, self.myrmex_cb)
        self.current_myrmex_state = None

        self.step_action_client = actionlib.SimpleActionClient("/mujoco_server/step", StepAction)
        self.step_action_client.wait_for_server()

        self.reset_client = rospy.ServiceProxy("/mujoco_server/reset", Empty)
        self.reset_client.wait_for_service()

        self.set_body_state_client = rospy.ServiceProxy("mujoco_server/set_body_state", SetBodyState)
        self.set_body_state_client.wait_for_service()

        self.get_body_state_client = rospy.ServiceProxy("/mujoco_server/get_body_state", GetBodyState)
        self.get_body_state_client.wait_for_service()

        self.mocap_state_publisher = rospy.Publisher("/mujoco_server/mocap_poses", MocapState, queue_size=100)

        rospy.rostime.wallsleep(0.5)

    def myrmex_cb(self, tactile_state: TactileState) -> None:
        self.current_myrmex_state = tactile_state

    def perform_steps_chunked(self, total_steps: int, step_chunk_size: int) -> Iterator[int]:
        for chunk in range(total_steps // step_chunk_size):
            self.perform_steps(num_steps=step_chunk_size)
            yield (chunk + 1) * step_chunk_size

    def perform_steps(self, num_steps: int) -> None:
        self.step_action_client.send_goal_and_wait(StepGoal(num_steps=num_steps))
        return self.step_action_client.get_result()

    def set_mocap_body(self, mocap_body_name: str, pose: Pose):
        mocap_state = MocapState()
        mocap_state.name = [mocap_body_name]
        mocap_state.pose = [pose.to_ros_pose()]
        mocap_state.pose[0].header.frame_id = "world"
        self.mocap_state_publisher.publish(mocap_state)

    def set_body_pose(self, body_name: str, pose: Pose):
        set_body_state_request = SetBodyStateRequest()
        set_body_state_request.state.name = body_name
        set_body_state_request.state.pose = pose.to_ros_pose()
        set_body_state_request.set_pose = True
        self.set_body_state_client.call(set_body_state_request)

    def get_body_pose_linvel(self, body_name: str) -> Tuple[Pose, np.ndarray]:
        request = GetBodyStateRequest()
        request.name = body_name
        while True:
            try:
                response: GetBodyStateResponse = self.get_body_state_client.call(request)
                pose = Pose.from_ros_pose(response.state.pose)
                linvel = response.state.twist.twist.linear
                linvel = np.array([linvel.x, linvel.y, linvel.z])
                return pose, linvel
            except:
                if rospy.is_shutdown():
                    break